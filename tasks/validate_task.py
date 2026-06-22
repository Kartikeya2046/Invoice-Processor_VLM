import asyncio
import asyncpg
import logging
from celery import shared_task
from core.celery_app import celery_app
from core.config import settings
from core.db import get_db_url, update_status_async
from validators.invoice_validator import validate_invoice_rules
from validators.boe_validator import validate_boe_rules
from validators.slm_validator import SLMValidator
from validators.confidence_scorer import merge_validation_results
from models.slm_client import SLMClient


logger = logging.getLogger(__name__)

async def save_validation_results_async(document_id: str, extraction_id: str, validation_result):
    conn = await asyncpg.connect(get_db_url())
    try:
        await conn.execute(
            """
            UPDATE extractions 
            SET overall_confidence = $1, requires_review = $2 
            WHERE id = $3
            """,
            validation_result.overall_confidence,
            validation_result.requires_review,
            extraction_id
        )
        
        for field in validation_result.fields:
            # Check if extracted_value column exists in field_confidences. Wait, the migration script 
            # had `extracted_value`, the pydantic model has `value`.
            val = field.value
            await conn.execute(
                """
                INSERT INTO field_confidences 
                (extraction_id, field_name, extracted_value, confidence, is_valid, validation_error)
                VALUES ($1, $2, $3, $4, $5, $6)
                """,
                extraction_id,
                field.field_name,
                str(val) if val is not None else None,
                field.confidence,
                field.confidence >= 0.75, # using confidence to determine is_valid
                field.flag
            )
            
        await conn.execute(
            "UPDATE documents SET status = 'completed', updated_at = NOW() WHERE id = $1",
            document_id
        )
    finally:
        await conn.close()

async def run_validation_pipeline(extraction_result: dict, document_id: str):
    await update_status_async(document_id, 'validating')
    
    doc_type = extraction_result["document_type"]
    extracted_fields = extraction_result["extracted_fields"]
    extraction_id = extraction_result["extraction_id"]
    
    # 1. Rule-based validation
    if doc_type == "invoice":
        from schemas.invoice import InvoiceSchema
        parsed_schema = InvoiceSchema(**extracted_fields)
        rule_results = validate_invoice_rules(parsed_schema)
    elif doc_type == "bill_of_entry":
        from schemas.bill_of_entry import BOESchema
        parsed_schema = BOESchema(**extracted_fields)
        rule_results = validate_boe_rules(parsed_schema)
    else:
        raise ValueError(f"Unknown document_type for validation: {doc_type}")
        
    # 2. SLM validation
    slm_client = SLMClient()
    slm_validator = SLMValidator(slm_client)
    slm_results = await slm_validator.validate(extracted_fields, doc_type)
    
    # 3. Merge results
    final_result = merge_validation_results(rule_results, slm_results, doc_type)
    
    # 4. Save results
    await save_validation_results_async(document_id, extraction_id, final_result)
    
    return final_result.model_dump()

@celery_app.task(bind=True, max_retries=2, default_retry_delay=15)
def validate_task(self, extraction_result: dict, document_id: str) -> dict:
    try:
        result = asyncio.run(run_validation_pipeline(extraction_result, document_id))
        from tasks.webhook_task import webhook_task
        webhook_task.delay(document_id)
        return result
    except Exception as e:
        asyncio.run(update_status_async(document_id, 'failed', 'validation', str(e)))
        from tasks.webhook_task import webhook_task
        webhook_task.delay(document_id)
        raise
