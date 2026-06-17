import os
import sys
import time
import base64
import logging
import asyncio
import argparse

# Enable INFO-level logging to see VLMClient timing and token logs
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Add the project root to sys.path so we can import from models and classifiers
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from models.vlm_client import VLMClient
from classifiers.vlm_classifier import VLMClassifier
from core.exceptions import DocumentUnknownError

def load_image_b64(path: str) -> str:
    if not os.path.exists(path):
        raise FileNotFoundError(f"File not found: {path}")
    with open(path, "rb") as f:
        image_bytes = f.read()
    return base64.b64encode(image_bytes).decode("utf-8")

async def main():
    parser = argparse.ArgumentParser(description="Test script for VLMClassifier")
    parser.add_argument("invoice_image", help="Path to an invoice image")
    parser.add_argument("--boe_image", default=None, help="Path to a bill of entry image (optional)")
    parser.add_argument("--garbage_image", default=None, help="Path to a non-document image (optional)")
    args = parser.parse_args()

    vlm_client = VLMClient()
    classifier = VLMClassifier(vlm_client)

    results = {
        "Invoice": "SKIPPED",
        "BOE": "SKIPPED",
        "Garbage": "SKIPPED"
    }
    any_failures = False

    print("\n======================================")
    print("1. INVOICE CHECK")
    print("======================================")
    try:
        b64_invoice = load_image_b64(args.invoice_image)
        start = time.perf_counter()
        result = await classifier.classify_document(b64_invoice)
        latency = time.perf_counter() - start
        
        print(f"Classification took {latency:.2f}s")
        print(f"Result returned: {result}")
        if result.document_type == "invoice":
            print("PASS")
            results["Invoice"] = "PASS"
        else:
            print(f"FAIL - Expected document_type to be 'invoice', got '{result.document_type}'")
            results["Invoice"] = "FAIL"
            any_failures = True
    except Exception as e:
        print(f"FAIL - Exception occurred: {e}")
        results["Invoice"] = "FAIL"
        any_failures = True

    print("\n======================================")
    print("2. BILL OF ENTRY CHECK")
    print("======================================")
    if not args.boe_image:
        print("SKIPPED — no BOE image provided")
    else:
        try:
            b64_boe = load_image_b64(args.boe_image)
            start = time.perf_counter()
            result = await classifier.classify_document(b64_boe)
            latency = time.perf_counter() - start
            
            print(f"Classification took {latency:.2f}s")
            print(f"Result returned: {result}")
            if result.document_type == "bill_of_entry":
                print("PASS")
                results["BOE"] = "PASS"
            else:
                print(f"FAIL - Expected document_type to be 'bill_of_entry', got '{result.document_type}'")
                results["BOE"] = "FAIL"
                any_failures = True
        except Exception as e:
            print(f"FAIL - Exception occurred: {e}")
            results["BOE"] = "FAIL"
            any_failures = True

    print("\n======================================")
    print("3. GARBAGE CHECK")
    print("======================================")
    if not args.garbage_image:
        print("SKIPPED — no garbage image provided")
    else:
        try:
            b64_garbage = load_image_b64(args.garbage_image)
            start = time.perf_counter()
            result = await classifier.classify_document(b64_garbage)
            latency = time.perf_counter() - start
            
            print(f"Classification took {latency:.2f}s")
            print(f"Result returned: {result}")
            print(f"FAIL - Model confidently misclassified garbage as a real document: {result}")
            results["Garbage"] = "FAIL"
            any_failures = True
        except DocumentUnknownError as e:
            print(f"PASS — DocumentUnknownError correctly raised: {e}")
            results["Garbage"] = "PASS"
        except Exception as e:
            print(f"FAIL - Expected DocumentUnknownError, but got a different exception: {e}")
            results["Garbage"] = "FAIL"
            any_failures = True

    print("\n======================================")
    print("SUMMARY TABLE")
    print("======================================")
    for check_name, status in results.items():
        print(f"{check_name.ljust(15)}: {status}")
    print("======================================")

    if any_failures:
        sys.exit(1)
    else:
        sys.exit(0)

if __name__ == "__main__":
    asyncio.run(main())
