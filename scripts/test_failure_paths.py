import os
import requests
import pytest
import time
import asyncio
import asyncpg
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import json
from datetime import datetime

API_KEY = os.environ.get("API_KEY", "9f86d081884c7d659a2feaa0c55ad015")
HEADERS = {"X-API-Key": API_KEY}

# Set up local environment for testing
os.environ["DATABASE_URL"] = "postgresql://postgres:postgres@localhost:5432/docextract"
os.environ["CELERY_BROKER_URL"] = "redis://localhost:6379/0"
os.environ["CELERY_RESULT_BACKEND"] = "redis://localhost:6379/1"

from tasks.webhook_task import webhook_task
from core.db import get_db_url
from core.config import settings

API_URL = "http://localhost:8000/documents"

class AlwaysFailWebhookHandler(BaseHTTPRequestHandler):
    received_payload = None

    def do_POST(self):
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        AlwaysFailWebhookHandler.received_payload = json.loads(post_data.decode('utf-8'))
        
        # Always return 500 to trigger max retries exhaustion
        self.send_response(500)
        self.end_headers()

class OneShotSuccessWebhookHandler(BaseHTTPRequestHandler):
    received_payload = None

    def do_POST(self):
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        OneShotSuccessWebhookHandler.received_payload = json.loads(post_data.decode('utf-8'))
        
        self.send_response(200)
        self.end_headers()

async def get_db_extraction_info(doc_id: str):
    conn = await asyncpg.connect(get_db_url())
    try:
        ext = await conn.fetchrow("SELECT * FROM extractions WHERE document_id = $1", doc_id)
        if ext:
            return dict(ext)
        return None
    finally:
        await conn.close()

async def get_db_doc_status(doc_id: str):
    conn = await asyncpg.connect(get_db_url())
    try:
        doc = await conn.fetchrow("SELECT status, webhook_delivered, webhook_attempts FROM documents WHERE id = $1", doc_id)
        if doc:
            return dict(doc)
        return None
    finally:
        await conn.close()

def test_extraction_failure():
    # 1. Start a local listener for the webhook
    OneShotSuccessWebhookHandler.received_payload = None
    server = HTTPServer(('0.0.0.0', 8086), OneShotSuccessWebhookHandler)
    server_thread = threading.Thread(target=server.serve_forever)
    server_thread.daemon = True
    server_thread.start()
    
    time.sleep(1) # wait for server
    
    try:
        # Submit unclassifiable garbage
        test_file_path = "test_data/garbage.png"
        if not os.path.exists(test_file_path):
            pytest.skip("Test fixture garbage.png not found")
            
        start_time = time.time()
        with open(test_file_path, "rb") as f:
            response = requests.post(
                API_URL,
                headers=HEADERS,
                files={"file": ("garbage.png", f, "image/png")},
                data={"callback_url": "http://host.docker.internal:8086/webhook"}
            )
        assert response.status_code == 200
        doc_id = response.json()["document_id"]
        
        # Poll status
        failed = False
        final_status = None
        for i in range(20): # Should fail fast (5-6s)
            res = requests.get(f"{API_URL}/{doc_id}/status", headers=HEADERS)
            if res.status_code == 200:
                s_data = res.json()
                if s_data["status"] == "failed":
                    failed = True
                    final_status = s_data
                    break
            time.sleep(1.0)
            
        latency = time.time() - start_time
        assert failed, "Document pipeline did not fail as expected"
        print(f"Extraction failure detected in {latency:.2f}s")
        assert latency < 15.0, "Expected fast failure (<15s) for extraction classification error"
        
        # Assert failure details
        assert final_status["failed_stage"] == "extraction"
        assert len(final_status["failure_reason"]) > 0
        
        # Assert validate_task never ran
        ext_info = asyncio.run(get_db_extraction_info(doc_id))
        assert ext_info is None, "Extraction row was created despite classification failure!"
        
        # Wait for webhook delivery
        time.sleep(3)
        assert OneShotSuccessWebhookHandler.received_payload is not None, "Listener never received webhook for failed task"
        
        # Assert webhook payload for failure
        payload = OneShotSuccessWebhookHandler.received_payload
        assert payload["document_id"] == doc_id
        assert payload["status"] == "failed"
        assert payload["failed_stage"] == "extraction"
        assert payload["result"] is None, "Expected result=null for failed extraction"
        
        print("test_extraction_failure passed successfully")
    finally:
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=2)


def test_webhook_exhaustion():
    # 1. Start local listener that ALWAYS fails
    AlwaysFailWebhookHandler.received_payload = None
    server = HTTPServer(('0.0.0.0', 8087), AlwaysFailWebhookHandler)
    server_thread = threading.Thread(target=server.serve_forever)
    server_thread.daemon = True
    server_thread.start()
    
    time.sleep(1) # Wait for server
    
    try:
        import uuid
        doc_id = str(uuid.uuid4())
        job_id = f"test-job-exhaust-{doc_id[:8]}"
        
        async def insert_doc():
            conn = await asyncpg.connect(get_db_url())
            try:
                await conn.execute(
                    """
                    INSERT INTO documents 
                    (id, job_id, original_path, file_name, file_size_bytes, mime_type, workflow, status, callback_url, document_type, webhook_delivered, webhook_attempts) 
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
                    """,
                    doc_id, job_id, "dummy/path", "dummy.pdf", 1024, "application/pdf", "default", "completed", "http://host.docker.internal:8087/webhook", "invoice", False, 0
                )
            finally:
                await conn.close()
                
        asyncio.run(insert_doc())
        
        # Temporarily patch settings for max_retries/backoff inside the container?
        # Actually we can't patch inside the container easily from here. 
        # We will use the actual MAX_RETRIES (default 4) and base 2.0.
        # Wait times: 2s + 4s + 8s + 16s = ~30s. We'll poll for ~45s.
        
        webhook_task.delay(doc_id)
        
        max_retries = settings.WEBHOOK_MAX_RETRIES
        print(f"Polling for {max_retries} max webhook retries exhaust... this will take ~45s")
        
        # Poll DB
        attempts = 0
        delivered = False
        start_time = time.time()
        
        last_attempts = 0
        exhausted = False
        
        while time.time() - start_time < 60: # 60s max
            doc_status = asyncio.run(get_db_doc_status(doc_id))
            if doc_status:
                delivered = doc_status["webhook_delivered"]
                attempts = doc_status["webhook_attempts"]
                if attempts == max_retries + 1:
                    # 1 initial + max_retries = max_retries + 1 total attempts
                    exhausted = True
                    break
            time.sleep(2.0)
            
        assert exhausted, f"Webhook did not exhaust retries. Expected {max_retries + 1} attempts, got {attempts}"
        assert delivered is False, "Webhook delivered was somehow True despite failing listener"
        
        # Verify it doesn't keep climbing
        time.sleep(5)
        doc_status_final = asyncio.run(get_db_doc_status(doc_id))
        assert doc_status_final["webhook_attempts"] == max_retries + 1, "Attempts kept climbing after exhaustion!"
        
        print("test_webhook_exhaustion passed successfully")
    finally:
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=2)


if __name__ == "__main__":
    test_extraction_failure()
    test_webhook_exhaustion()
