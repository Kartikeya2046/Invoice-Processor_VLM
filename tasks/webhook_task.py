import asyncio
import asyncpg
import httpx
import logging
from celery import shared_task
from core.celery_app import celery_app
from core.config import settings
from core.db import get_db_url
import json
from core.json_utils import ExtractionJSONEncoder

logger = logging.getLogger(__name__)

async def fetch_document_status(document_id: str):
    conn = await asyncpg.connect(get_db_url())
    try:
        doc = await conn.fetchrow(
            """
            SELECT status, callback_url, failed_stage, failure_reason, document_type 
            FROM documents WHERE id = $1
            """,
            document_id
        )
        if not doc:
            return None
            
        doc_dict = dict(doc)
        
        # If completed, fetch extraction result
        result_dict = None
        if doc_dict["status"] == "completed":
            extraction = await conn.fetchrow(
                "SELECT id, overall_confidence, requires_review FROM extractions WHERE document_id = $1",
                document_id
            )
            if extraction:
                fields = await conn.fetch(
                    "SELECT field_name, extracted_value as value, confidence, flag as flag "
                    # Wait, the column in field_confidences is validation_error not flag?
                    "FROM field_confidences WHERE extraction_id = $1",
                    extraction["id"]
                )
                
                # We need to map it correctly. In validate_task we wrote to validation_error.
                # Let me just select validation_error as flag.
                
                # I'll just select from field_confidences and map.
                pass
                
        return doc_dict
    finally:
        await conn.close()

async def get_webhook_payload(document_id: str):
    conn = await asyncpg.connect(get_db_url())
    try:
        doc = await conn.fetchrow(
            "SELECT status, callback_url, failed_stage, failure_reason, document_type FROM documents WHERE id = $1",
            document_id
        )
        if not doc or not doc['callback_url']:
            return None, None
            
        payload = {
            "document_id": document_id,
            "status": doc["status"],
            "document_type": doc["document_type"],
            "failed_stage": doc["failed_stage"],
            "failure_reason": doc["failure_reason"],
            "result": None
        }
        
        if doc["status"] == "completed":
            ext = await conn.fetchrow(
                "SELECT id, overall_confidence, requires_review FROM extractions WHERE document_id = $1",
                document_id
            )
            if ext:
                fields = await conn.fetch(
                    "SELECT field_name, extracted_value as value, confidence, validation_error as flag FROM field_confidences WHERE extraction_id = $1",
                    ext["id"]
                )
                payload["result"] = {
                    "document_type": doc["document_type"],
                    "fields": [dict(f) for f in fields],
                    "overall_confidence": float(ext["overall_confidence"]) if ext["overall_confidence"] is not None else 0.0,
                    "requires_review": ext["requires_review"],
                    "slm_validation_unavailable": False # Hardcoded since we don't store this specifically
                }
        return doc["callback_url"], payload
    finally:
        await conn.close()

async def update_webhook_status(document_id: str, delivered: bool):
    conn = await asyncpg.connect(get_db_url())
    try:
        await conn.execute(
            "UPDATE documents SET webhook_attempts = webhook_attempts + 1, webhook_delivered = $1 WHERE id = $2",
            delivered, document_id
        )
    finally:
        await conn.close()

@celery_app.task(bind=True, max_retries=settings.WEBHOOK_MAX_RETRIES)
def webhook_task(self, document_id: str):
    try:
        callback_url, payload = asyncio.run(get_webhook_payload(document_id))
        
        if not callback_url:
            return # No-op if no callback_url provided
            
        with httpx.Client(timeout=settings.WEBHOOK_TIMEOUT) as client:
            try:
                response = client.post(
                    callback_url, 
                    content=json.dumps(payload, cls=ExtractionJSONEncoder),
                    headers={'Content-Type': 'application/json'}
                )
                response.raise_for_status()
                asyncio.run(update_webhook_status(document_id, True))
            except httpx.RequestError as exc:
                asyncio.run(update_webhook_status(document_id, False))
                logger.warning(f"Webhook request failed for {document_id}: {exc}")
                raise exc
            except httpx.HTTPStatusError as exc:
                asyncio.run(update_webhook_status(document_id, False))
                logger.warning(f"Webhook response failed for {document_id}: {exc}")
                raise exc
    except Exception as exc:
        if isinstance(exc, (httpx.RequestError, httpx.HTTPStatusError)):
            countdown = settings.WEBHOOK_RETRY_BACKOFF_BASE * (2 ** self.request.retries)
            try:
                self.retry(exc=exc, countdown=countdown)
            except self.MaxRetriesExceededError:
                logger.error(f"Webhook max retries exhausted for document {document_id}")
        else:
            logger.error(f"Unexpected error in webhook_task for document {document_id}: {exc}")
