import os
import requests
import pytest
import time

API_KEY = os.environ.get("API_KEY", "9f86d081884c7d659a2feaa0c55ad015")
HEADERS = {"X-API-Key": API_KEY}

API_URL = "http://localhost:8000/documents"

def get_or_create_review_document():
    # Attempt to find an existing one first
    res = requests.get(f"{API_URL}/review", params={"status": "completed", "limit": 1}, headers=HEADERS)
    if res.status_code == 200:
        data = res.json()
        if data["total"] > 0:
            return data["items"][0]["document_id"]
            
    # Need to create one since boe.png doesn't actually fail
    import uuid
    import asyncio
    import asyncpg
    from core.db import get_db_url
    
    doc_id = str(uuid.uuid4())
    async def inject_bad_doc():
        conn = await asyncpg.connect(os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/docextract"))
        try:
            # Insert document
            await conn.execute(
                """
                INSERT INTO documents (id, job_id, original_path, file_name, file_size_bytes, mime_type, workflow, status, callback_url, document_type, webhook_delivered, webhook_attempts) 
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
                """,
                doc_id, f"test-job-{doc_id[:8]}", "dummy/path", "dummy.pdf", 1024, "application/pdf", "default", "completed", "http://localhost:8085/webhook", "bill_of_entry", False, 0
            )
            # Insert extraction
            ext_id = str(uuid.uuid4())
            await conn.execute(
                """
                INSERT INTO extractions (id, document_id, overall_confidence, requires_review)
                VALUES ($1, $2, $3, $4)
                """,
                ext_id, doc_id, 0.88, True
            )
            # Insert field
            await conn.execute(
                """
                INSERT INTO field_confidences (id, extraction_id, field_name, confidence, validation_error)
                VALUES ($1, $2, $3, $4, $5)
                """,
                str(uuid.uuid4()), ext_id, "sbcess", 0.1, "rule_failed"
            )
            await conn.execute(
                """
                INSERT INTO field_confidences (id, extraction_id, field_name, confidence, validation_error)
                VALUES ($1, $2, $3, $4, $5)
                """,
                str(uuid.uuid4()), ext_id, "igst", 1.0, None
            )
        finally:
            await conn.close()
    
    asyncio.run(inject_bad_doc())
    return doc_id

def test_review_queue():
    doc_id = get_or_create_review_document()
    
    # Assert GET /documents/review with no query params
    res = requests.get(f"{API_URL}/review", headers=HEADERS)
    assert res.status_code == 200
    data = res.json()
    
    # It must contain the doc_id in items
    items = data["items"]
    target_item = next((item for item in items if item["document_id"] == doc_id), None)
    assert target_item is not None, f"Document {doc_id} not found in review queue"
    
    # Assert summary shape and contents
    assert "flagged_fields" in target_item
    assert isinstance(target_item["flagged_fields"], list)
    assert len(target_item["flagged_fields"]) > 0, "Expected at least one flagged field"
    # Note: Full ExtractionResult should not be here
    assert "fields" not in target_item, "Full extraction result 'fields' should not be duplicated in summary"
    
    # Assert Pagination
    res_paginated = requests.get(f"{API_URL}/review", params={"limit": 1}, headers=HEADERS)
    assert res_paginated.status_code == 200
    paginated_data = res_paginated.json()
    assert len(paginated_data["items"]) <= 1, f"Expected 1 item, got {len(paginated_data['items'])}"
    assert paginated_data["limit"] == 1
    
    # Assert Filter params
    # We assume doc_id is a bill_of_entry since it's boe.png
    res_filter = requests.get(f"{API_URL}/review", params={"doc_type": "invoice"}, headers=HEADERS)
    assert res_filter.status_code == 200
    filter_data = res_filter.json()
    assert next((item for item in filter_data["items"] if item["document_id"] == doc_id), None) is None, "Document found in review queue with wrong doc_type filter"
    
    print("test_review_queue passed successfully")

if __name__ == "__main__":
    test_review_queue()
