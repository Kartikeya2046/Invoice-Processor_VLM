import os
import json
import base64
import asyncio
import httpx
import asyncpg
from celery import shared_task
from core.celery_app import celery_app
from core.config import settings
from core.exceptions import DocumentUnknownError, ExtractionError
from models.vlm_client import VLMClient, VLMClientError
from classifiers.vlm_classifier import VLMClassifier
from extractors.invoice import InvoiceExtractor
from extractors.bill_of_entry import BOEExtractor
from core.db import get_db_url, update_status_async

async def get_document_async(document_id: str):
    conn = await asyncpg.connect(get_db_url())
    try:
        row = await conn.fetchrow("SELECT original_path, mime_type FROM documents WHERE id = $1", document_id)
        return row
    finally:
        await conn.close()

async def save_extraction_async(document_id: str, document_type: str, raw_output: str):
    conn = await asyncpg.connect(get_db_url())
    try:
        await conn.execute("UPDATE documents SET document_type = $1 WHERE id = $2", document_type, document_id)
        # We don't have requires_review or overall_confidence until validation, so just save extracted_json as raw for now?
        # Actually spec says "save to existing extractions table".
        # Let's insert into extractions table.
        row = await conn.fetchrow(
            """
            INSERT INTO extractions (document_id, extracted_json) 
            VALUES ($1, $2) 
            RETURNING id
            """,
            document_id, raw_output
        )
        return row["id"]
    finally:
        await conn.close()

async def run_extraction_pipeline(document_id: str):
    # 1. Load document
    doc = await get_document_async(document_id)
    if not doc:
        raise ValueError(f"Document {document_id} not found")
        
    path = doc["original_path"]
    with open(path, "rb") as f:
        image_b64 = base64.b64encode(f.read()).decode("utf-8")
        
    # 2. Update status
    await update_status_async(document_id, 'extracting')
    
    vlm_client = VLMClient()
    classifier = VLMClassifier(vlm_client)
    
    # 3. Classify
    classification = await classifier.classify_document(image_b64)
    doc_type = classification.document_type
    
    # 4. Extract
    if doc_type == "invoice":
        extractor = InvoiceExtractor(vlm_client)
        result = await extractor.extract(image_b64)
    elif doc_type == "bill_of_entry":
        extractor = BOEExtractor(vlm_client)
        result = await extractor.extract(image_b64)
    else:
        raise DocumentUnknownError(f"Cannot extract unknown document type: {doc_type}")
        
    # 5. Save extraction result
    raw_json = result.model_dump_json()
    extraction_id = await save_extraction_async(document_id, doc_type, raw_json)
    
    return {
        "document_id": document_id,
        "document_type": doc_type,
        "extraction_id": str(extraction_id),
        "extracted_fields": result.model_dump()
    }

@celery_app.task(bind=True, max_retries=3, default_retry_delay=10)
def extract_task(self, document_id: str) -> dict:
    try:
        # Run the async pipeline synchronously
        return asyncio.run(run_extraction_pipeline(document_id))
        
    except (DocumentUnknownError, ExtractionError, ValueError) as e:
        # Permanent errors
        asyncio.run(update_status_async(document_id, 'failed', 'extraction', str(e)))
        from tasks.webhook_task import webhook_task
        webhook_task.delay(document_id)
        raise
        
    except VLMClientError as e:
        # Check if it wraps a transient error from httpx
        is_transient = False
        if e.__cause__:
            cause = e.__cause__
            if isinstance(cause, httpx.TimeoutException) or isinstance(cause, httpx.ConnectError):
                is_transient = True
            elif isinstance(cause, httpx.HTTPStatusError) and cause.response.status_code >= 500:
                is_transient = True
                
        if is_transient:
            try:
                self.retry(exc=e)
            except self.MaxRetriesExceededError:
                pass
                
        # If not transient or max retries exceeded, it's a hard failure
        asyncio.run(update_status_async(document_id, 'failed', 'extraction', str(e)))
        from tasks.webhook_task import webhook_task
        webhook_task.delay(document_id)
        raise

    except Exception as e:
        # Any other unexpected exception
        asyncio.run(update_status_async(document_id, 'failed', 'extraction', str(e)))
        from tasks.webhook_task import webhook_task
        webhook_task.delay(document_id)
        raise
