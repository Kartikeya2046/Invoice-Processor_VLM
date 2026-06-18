import os
import sys
import time
import base64
import logging
import asyncio
import argparse

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from models.vlm_client import VLMClient
from extractors.invoice import InvoiceExtractor
from core.exceptions import ExtractionError

def load_image_b64(path: str) -> str:
    if not os.path.exists(path):
        raise FileNotFoundError(f"File not found: {path}")
    with open(path, "rb") as f:
        image_bytes = f.read()
    return base64.b64encode(image_bytes).decode("utf-8")

async def main():
    parser = argparse.ArgumentParser(description="Test script for InvoiceExtractor")
    parser.add_argument("invoice_image", help="Path to an invoice image")
    args = parser.parse_args()

    vlm_client = VLMClient()
    extractor = InvoiceExtractor(vlm_client)

    print("\n======================================")
    print("INVOICE EXTRACTION CHECK")
    print("======================================")
    
    try:
        b64_invoice = load_image_b64(args.invoice_image)
        start = time.perf_counter()
        result = await extractor.extract(b64_invoice)
        latency = time.perf_counter() - start
        
        print(f"Extraction took {latency:.2f}s")
        print("Extracted Data:")
        for field, value in result.model_dump().items():
            print(f"  {field}: {value}")
            
        if result.invoice_number is not None and result.supplier is not None:
            print("PASS")
            sys.exit(0)
        else:
            print("FAIL - invoice_number or supplier is null")
            sys.exit(1)
    except Exception as e:
        print(f"FAIL - Exception occurred: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
