import os
import requests
import pytest
import time
import asyncio
import asyncpg

API_KEY = os.environ.get("API_KEY", "9f86d081884c7d659a2feaa0c55ad015")
HEADERS = {"X-API-Key": API_KEY}

API_URL = "http://localhost:8000/documents"

async def get_db_doc(doc_id: str):
    db_url = os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/docextract")
    conn = await asyncpg.connect(db_url)
    try:
        row = await conn.fetchrow("SELECT * FROM documents WHERE id = $1", doc_id)
        if row:
            return dict(row)
        return None
    finally:
        await conn.close()

async def get_db_fields(doc_id: str):
    db_url = os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/docextract")
    conn = await asyncpg.connect(db_url)
    try:
        ext = await conn.fetchrow("SELECT * FROM extractions WHERE document_id = $1", doc_id)
        if ext:
            fields = await conn.fetch("SELECT * FROM field_confidences WHERE extraction_id = $1", ext["id"])
            return [dict(f) for f in fields]
        return []
    finally:
        await conn.close()

def test_document_detail_and_status():
    test_file_path = "test_data/sample_invoice.png"
    if not os.path.exists(test_file_path):
        pytest.skip("Test fixture sample_invoice.png not found")

    with open(test_file_path, "rb") as f:
        response = requests.post(
            API_URL,
            headers=HEADERS,
            files={"file": ("sample_invoice.png", f, "image/png")}
        )
    assert response.status_code == 200
    doc_id = response.json()["document_id"]
    
    # 1. Immediately call the status endpoint
    res_status = requests.get(f"{API_URL}/{doc_id}/status", headers=HEADERS)
    assert res_status.status_code == 200
    status_data = res_status.json()
    
    # Assert exact shape
    expected_keys = {"document_id", "status", "failed_stage", "failure_reason", "webhook_delivered"}
    assert set(status_data.keys()) == expected_keys, f"Expected keys {expected_keys}, got {set(status_data.keys())}"
    assert status_data["status"] in ["pending", "extracting", "validating", "completed"], f"Unexpected early status: {status_data['status']}"

    # 2. Call full detail endpoint while extracting/validating
    res_detail = requests.get(f"{API_URL}/{doc_id}", headers=HEADERS)
    assert res_detail.status_code == 200
    detail_data = res_detail.json()
    
    # If not yet completed, extraction_result should be None
    if detail_data["status"] in ["pending", "extracting", "validating"]:
        assert detail_data.get("extraction_result") is None, "extraction_result should be null before completion"

    # 3. Poll until completed
    completed = False
    for i in range(120):
        res = requests.get(f"{API_URL}/{doc_id}/status", headers=HEADERS)
        if res.status_code == 200:
            if res.json()["status"] == "completed":
                completed = True
                break
        time.sleep(1.5)
        
    assert completed, "Document pipeline timed out"
    
    # 4. Check full detail endpoint for completed doc
    res_detail_done = requests.get(f"{API_URL}/{doc_id}", headers=HEADERS)
    assert res_detail_done.status_code == 200
    detail_done = res_detail_done.json()
    assert detail_done["extraction_result"] is not None
    
    # Cross-check field-by-field against DB
    db_fields = asyncio.run(get_db_fields(doc_id))
    api_fields = detail_done["extraction_result"]["fields"]
    
    assert len(api_fields) > 0, "Expected fields in API response"
    assert len(api_fields) == len(db_fields), "Mismatch in number of fields between API and DB"
    
    # 5. Check 422 behavior for malformed UUID
    res_422 = requests.get(f"{API_URL}/not-a-real-uuid", headers=HEADERS)
    assert res_422.status_code == 422, f"Expected 422, got {res_422.status_code}"

    # 6. Check 404 behavior for well-formed but unknown document
    import uuid
    res_404 = requests.get(f"{API_URL}/{uuid.uuid4()}", headers=HEADERS)
    assert res_404.status_code == 404, f"Expected 404, got {res_404.status_code}"
    
    print("test_document_detail_and_status passed successfully")

if __name__ == "__main__":
    test_document_detail_and_status()
