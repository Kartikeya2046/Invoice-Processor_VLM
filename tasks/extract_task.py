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
        row = await conn.fetchrow("""
            SELECT d.original_path, d.mime_type, p.page_count, p.page_image_paths 
            FROM documents d
            LEFT JOIN processing_metadata p ON d.id = p.document_id
            WHERE d.id = $1
            """, document_id)
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

async def save_page_extraction_async(document_id: str, document_type: str, raw_output: str, page_number: int, extracted_fields: dict):
    conn = await asyncpg.connect(get_db_url())
    try:
        await conn.execute("UPDATE documents SET document_type = $1 WHERE id = $2", document_type, document_id)
        
        row = await conn.fetchrow(
            """
            INSERT INTO extractions (document_id, extracted_json, page_number) 
            VALUES ($1, $2, $3) 
            RETURNING id
            """,
            document_id, raw_output, page_number
        )
        ext_id = row["id"]
        
        # Save field confidences with NULL confidence
        for field_name, value in extracted_fields.items():
            await conn.execute(
                """
                INSERT INTO field_confidences (extraction_id, field_name, extracted_value, page_number)
                VALUES ($1, $2, $3, $4)
                """,
                ext_id, field_name, str(value) if value is not None else None, page_number
            )
            
        return ext_id
    finally:
        await conn.close()

async def run_extraction_pipeline(document_id: str):
    # 1. Load document
    doc = await get_document_async(document_id)
    if not doc:
        raise ValueError(f"Document {document_id} not found")
        
    await update_status_async(document_id, 'extracting')
    
    vlm_client = VLMClient()
    classifier = VLMClassifier(vlm_client)
    
    page_count = doc["page_count"] or 1
    paths_str = doc["page_image_paths"]
    
    if paths_str:
        if isinstance(paths_str, str):
            page_image_paths = json.loads(paths_str)
        else:
            page_image_paths = paths_str
    else:
        page_image_paths = [doc["original_path"]]

    if page_count == 1:
        path = page_image_paths[0]
        with open(path, "rb") as f:
            image_b64 = base64.b64encode(f.read()).decode("utf-8")
            
        classification = await classifier.classify_document(image_b64)
        doc_type = classification.document_type
        
        if doc_type == "invoice":
            extractor = InvoiceExtractor(vlm_client)
            result = await extractor.extract(image_b64)
        elif doc_type == "bill_of_entry":
            extractor = BOEExtractor(vlm_client)
            result = await extractor.extract(image_b64)
        else:
            raise DocumentUnknownError(f"Cannot extract unknown document type: {doc_type}")
            
        raw_json = result.model_dump_json()
        extraction_id = await save_extraction_async(document_id, doc_type, raw_json)
        
        return {
            "document_id": document_id,
            "document_type": doc_type,
            "extraction_id": str(extraction_id),
            "extracted_fields": result.model_dump()
        }
    else:
        # Multi-page extraction
        first_page_extraction_id = None
        first_page_doc_type = None
        first_page_result = None
        
        all_failed = True
        for i, path in enumerate(page_image_paths):
            page_number = i + 1
            with open(path, "rb") as f:
                image_b64 = base64.b64encode(f.read()).decode("utf-8")
                
            try:
                classification = await classifier.classify_document(image_b64)
                doc_type = classification.document_type
            except Exception:
                # Fallback if classification fails entirely on a page
                doc_type = "unknown"
                
            result = None
            if doc_type == "invoice":
                extractor = InvoiceExtractor(vlm_client)
                try:
                    result = await extractor.extract(image_b64)
                except Exception:
                    pass
            elif doc_type == "bill_of_entry":
                extractor = BOEExtractor(vlm_client)
                try:
                    result = await extractor.extract(image_b64)
                except Exception:
                    pass
                    
            if result:
                all_failed = False
                raw_json = result.model_dump_json()
                ext_id = await save_page_extraction_async(document_id, doc_type, raw_json, page_number, result.model_dump())
                
                if first_page_extraction_id is None:
                    first_page_extraction_id = ext_id
                    first_page_doc_type = doc_type
                    first_page_result = result.model_dump()
            else:
                await save_page_extraction_async(document_id, doc_type, "{}", page_number, {})
                
        if all_failed:
            raise ExtractionError("All pages failed to extract")
            
        # TODO Step D: replace with merged result
        return {
            "document_id": document_id,
            "document_type": first_page_doc_type or "unknown",
            "extraction_id": str(first_page_extraction_id) if first_page_extraction_id else "",
            "extracted_fields": first_page_result or {}
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
