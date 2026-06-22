import asyncio
import json
import uuid
import threading
import time
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
import pytest
import asyncpg
import os
os.environ["DATABASE_URL"] = "postgresql://postgres:postgres@localhost:5432/docextract"
os.environ["CELERY_BROKER_URL"] = "redis://localhost:6379/0"
os.environ["CELERY_RESULT_BACKEND"] = "redis://localhost:6379/1"

from tasks.webhook_task import webhook_task
from core.db import get_db_url

class WebhookTestHandler(BaseHTTPRequestHandler):
    fail_count = 0
    received_payload = None
    request_timestamps = []

    def do_POST(self):
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        
        WebhookTestHandler.received_payload = json.loads(post_data.decode('utf-8'))
        WebhookTestHandler.request_timestamps.append(time.time())
        
        print(f"[{datetime.now().isoformat()}] Webhook server received POST. fail_count left: {WebhookTestHandler.fail_count}")

        if WebhookTestHandler.fail_count > 0:
            WebhookTestHandler.fail_count -= 1
            self.send_response(500)
            self.end_headers()
        else:
            self.send_response(200)
            self.end_headers()

def run_server(server_class=HTTPServer, handler_class=WebhookTestHandler, port=8085):
    server_address = ('', port)
    httpd = server_class(server_address, handler_class)
    httpd.serve_forever()

async def setup_test_document():
    doc_id = str(uuid.uuid4())
    job_id = f"test-job-{doc_id[:8]}"
    
    conn = await asyncpg.connect(get_db_url())
    try:
        await conn.execute(
            """
            INSERT INTO documents 
            (id, job_id, original_path, file_name, file_size_bytes, mime_type, workflow, status, callback_url, document_type, webhook_delivered, webhook_attempts) 
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
            """,
            doc_id, job_id, "dummy/path", "dummy.pdf", 1024, "application/pdf", "default", "completed", "http://host.docker.internal:8085/webhook", "invoice", False, 0
        )
        return doc_id
    finally:
        await conn.close()

async def poll_webhook_status(doc_id: str, timeout: int = 45):
    conn = await asyncpg.connect(get_db_url())
    try:
        start_time = time.time()
        while time.time() - start_time < timeout:
            row = await conn.fetchrow(
                "SELECT webhook_delivered, webhook_attempts FROM documents WHERE id = $1",
                doc_id
            )
            if row["webhook_delivered"] is True:
                return dict(row)
            await asyncio.sleep(2)
        
        # If we hit timeout, return the last known state
        row = await conn.fetchrow(
            "SELECT webhook_delivered, webhook_attempts FROM documents WHERE id = $1",
            doc_id
        )
        return dict(row) if row else None
    finally:
        await conn.close()

def test_webhook_delivery():
    # Start mock server
    WebhookTestHandler.fail_count = 2 # Fail twice, then succeed
    WebhookTestHandler.received_payload = None
    WebhookTestHandler.request_timestamps = []
    
    server = HTTPServer(('0.0.0.0', 8085), WebhookTestHandler)
    server_thread = threading.Thread(target=server.serve_forever)
    server_thread.daemon = True
    server_thread.start()
    
    time.sleep(1) # Wait for server to start
    
    try:
        doc_id = asyncio.run(setup_test_document())
        
        print(f"[{datetime.now().isoformat()}] Test document inserted: {doc_id}. Dispatching task to Celery...")
        
        # Dispatch to real celery worker
        webhook_task.delay(doc_id)
        
        print(f"[{datetime.now().isoformat()}] Polling database for status updates (timeout 45s)...")
        # Poll DB
        final_status = asyncio.run(poll_webhook_status(doc_id, timeout=45))
        
        print(f"[{datetime.now().isoformat()}] Polling finished. DB Status: {final_status}")
        
        # Asserts
        assert WebhookTestHandler.received_payload is not None, "Listener never received the payload"
        assert WebhookTestHandler.received_payload["document_id"] == doc_id, "Listener received payload for wrong document"
        
        assert final_status is not None, "Document disappeared from DB"
        assert final_status["webhook_attempts"] == 3, f"Expected 3 attempts, got {final_status['webhook_attempts']}"
        assert final_status["webhook_delivered"] is True, "webhook_delivered should be True"
        
        # Optionally, check timestamps (base=2.0 -> attempts delay at least 2s then 4s, etc depending on config)
        if len(WebhookTestHandler.request_timestamps) >= 3:
            gap1 = WebhookTestHandler.request_timestamps[1] - WebhookTestHandler.request_timestamps[0]
            gap2 = WebhookTestHandler.request_timestamps[2] - WebhookTestHandler.request_timestamps[1]
            print(f"Time gaps between attempts: {gap1:.2f}s, {gap2:.2f}s")
    
    finally:
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=2)
