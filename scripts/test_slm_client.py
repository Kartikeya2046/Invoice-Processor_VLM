import os
import sys
import asyncio
import httpx
import logging

# Enable INFO-level logging so the client's internal logs print to the console
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from models.slm_client import SLMClient
from core.config import settings

async def main():
    print("--- SLM CLIENT CHECK ---")
    
    url = f"{settings.SLM_ENDPOINT.rstrip('/')}/api/tags"
    try:
        response = httpx.get(url, timeout=5.0)
        response.raise_for_status()
        print("SLM ENDPOINT: REACHABLE")
    except Exception as e:
        print("SLM ENDPOINT: UNREACHABLE")
        print(f"Error: {e}")
        sys.exit(1)

    slm_client = SLMClient()
    
    try:
        response_text = await slm_client.validate(
            extracted_json={"test": "ping"},
            document_type="invoice",
            prompt="You are a helpful assistant. Reply with exactly the word OK and nothing else."
        )
        print("Raw Response:")
        print(response_text)
        
        if response_text and isinstance(response_text, str) and response_text.strip():
            print("PASS")
        else:
            print("FAIL: Returned response is empty")
    except Exception as e:
        print(f"FAIL: {e}")

if __name__ == "__main__":
    asyncio.run(main())
