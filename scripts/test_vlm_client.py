import os
import sys
import time
import base64
import logging
import asyncio
import argparse

# Enable INFO-level logging so the client's internal logs print to the console
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Add the project root to sys.path so we can import models.vlm_client if run from elsewhere
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from models.vlm_client import VLMClient, VLMClientError

async def main():
    parser = argparse.ArgumentParser(description="Test script for VLMClient")
    parser.add_argument("image_path", help="Path to the invoice/document image")
    args = parser.parse_args()

    image_path = args.image_path
    if not os.path.exists(image_path):
        print(f"Error: File not found at {image_path}")
        sys.exit(1)

    # Infer MIME type from extension
    ext = os.path.splitext(image_path)[1].lower()
    if ext in ['.jpg', '.jpeg']:
        mime_type = "image/jpeg"
    elif ext == '.png':
        mime_type = "image/png"
    else:
        print(f"Error: Unsupported extension '{ext}'. Only .png and .jpg/.jpeg are supported.")
        sys.exit(1)

    # Read and encode image
    with open(image_path, "rb") as f:
        image_bytes = f.read()
    image_b64 = base64.b64encode(image_bytes).decode("utf-8")

    client = VLMClient()

    # Health check
    print("Performing health check...")
    is_healthy = await client.health_check()
    print(f"Health check: {is_healthy}")
    if not is_healthy:
        print("Error: VLM health check returned False. Exiting.")
        sys.exit(1)

    # Run tests
    try:
        print("\n--- Running Classify ---")
        classify_start = time.perf_counter()
        classify_result = await client.classify(image_b64, mime_type=mime_type)
        classify_latency = time.perf_counter() - classify_start
        print(f"Classify completed in {classify_latency:.2f}s")
        print("Classify Result:", classify_result)

        print("\n--- Running Extract ---")
        schema = '{"vendor": "string", "invoice_number": "string", "total_amount": "number"}'
        prompt = "Extract the vendor name, invoice number, and total amount from this invoice."
        
        extract_start = time.perf_counter()
        extract_result = await client.extract(image_b64, prompt, schema, mime_type=mime_type)
        extract_latency = time.perf_counter() - extract_start
        print(f"Extract completed in {extract_latency:.2f}s")
        print("Extract Result (Raw String):")
        print(extract_result)

    except VLMClientError as e:
        print(f"\n[!] VLMClientError encountered: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n[!] Unexpected Error: {e}")
        sys.exit(1)

    # Success reminder
    print("\nCheck the INFO logs above for prompt_tokens — if near 2048, max_tokens or image resolution may need further tuning.")
    sys.exit(0)

if __name__ == "__main__":
    asyncio.run(main())
