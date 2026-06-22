import os
os.environ["DATABASE_URL"] = "postgresql://postgres:postgres@localhost:5432/docextract"

from fastapi.testclient import TestClient
from api.main import app
from unittest.mock import patch
import pytest

client = TestClient(app)

def test_get_review_queue_route_ordering():
    # If route ordering is wrong, this will hit /{document_id} and likely throw 422 or 500
    # because 'review' is not a valid UUID (if document_id is typed as UUID) or it will try to look up 'review' in the DB.
    # We mock the database connection to avoid actual DB calls.
    
    from unittest.mock import AsyncMock
    with patch('api.routes.documents.asyncpg.connect', new_callable=AsyncMock) as mock_connect:
        mock_conn = mock_connect.return_value
        # Mock for get_review_queue
        mock_conn.fetchval = AsyncMock(return_value=0)
        mock_conn.fetch = AsyncMock(return_value=[])
        mock_conn.close = AsyncMock()
        
        API_KEY = os.environ.get("API_KEY", "9f86d081884c7d659a2feaa0c55ad015")
        response = client.get("/documents/review", headers={"X-API-Key": API_KEY})
        assert response.status_code == 200, f"Expected 200, got {response.status_code}. Response: {response.text}"
        
        data = response.json()
        assert "items" in data
        assert "total" in data
