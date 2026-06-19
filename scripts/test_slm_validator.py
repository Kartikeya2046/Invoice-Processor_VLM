import os
import sys
import asyncio

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from models.slm_client import SLMClient
from validators.slm_validator import SLMValidator

async def main():
    print("--- SLM VALIDATOR CHECK ---")
    summary = []

    slm_client = SLMClient()
    slm_validator = SLMValidator(slm_client)

    # Test 1: Known-Good Invoice
    print("\n--- Test 1: Known-Good Invoice ---")
    extracted_json_invoice = {
        "po_number": None,
        "supplier": "Ricci Microwave Co., Ltd.",
        "invoice_number": "R202209-12",
        "invoice_date": "2022-09-12",
        "quantity": 1000.0,
        "unit_price": 55.7,
        "cgst": None,
        "sgst": None
    }
    
    try:
        results1 = await slm_validator.validate(extracted_json_invoice, "invoice")
        if results1:
            for res in results1:
                print(f"  Field: {res.field_name:15} | Conf: {res.confidence:.1f} | Flag: {res.flag}")
            print("PASS: Non-empty list returned")
            summary.append(("Test 1: Known-Good Invoice", "PASS"))
        else:
            print("FAIL: Returned [] (call failed)")
            summary.append(("Test 1: Known-Good Invoice", "FAIL"))
    except Exception as e:
        print(f"FAIL: Exception raised: {e}")
        summary.append(("Test 1: Known-Good Invoice", "FAIL"))

    # Test 2: Known-Bad BOE
    print("\n--- Test 2: Known-Bad BOE (sbcess error) ---")
    extracted_json_boe = {
        "boe_number": "7842531",
        "boe_date": "2024-03-14",
        "igst": 69588.0,
        "cust_duty": 35145.0,
        "sbcess": 35145.0
    }

    try:
        results2 = await slm_validator.validate(extracted_json_boe, "bill_of_entry")
        if results2:
            for res in results2:
                print(f"  Field: {res.field_name:15} | Conf: {res.confidence:.1f} | Flag: {res.flag}")
            
            sbcess_flagged = any(
                res.field_name == "sbcess" and res.confidence < 0.7 
                for res in results2
            )
            if sbcess_flagged:
                print("INFO: SLM caught the issue (sbcess confidence < 0.7)")
            else:
                print("INFO: SLM did not flag this — note for review")
                
            print("PASS: Call completed and returned list")
            summary.append(("Test 2: Known-Bad BOE", "PASS"))
        else:
            print("FAIL: Returned [] (call failed)")
            summary.append(("Test 2: Known-Bad BOE", "FAIL"))
    except Exception as e:
        print(f"FAIL: Exception raised: {e}")
        summary.append(("Test 2: Known-Bad BOE", "FAIL"))

    # Test 3: Simulated Unreachable Endpoint
    print("\n--- Test 3: Simulated Unreachable Endpoint ---")
    broken_client = SLMClient()
    broken_client.endpoint = "https://nonexistent.invalid"
    broken_client.max_retries = 1  # Reduced max_retries for faster test
    broken_validator = SLMValidator(broken_client)
    
    try:
        results3 = await broken_validator.validate(extracted_json_invoice, "invoice")
        if results3 == []:
            print("PASS: Returned [] on failure without propagating exception")
            summary.append(("Test 3: Unreachable Endpoint", "PASS"))
        else:
            print("FAIL: Expected [], got something else")
            summary.append(("Test 3: Unreachable Endpoint", "FAIL"))
    except Exception as e:
        print(f"FAIL: Exception propagated out: {e}")
        summary.append(("Test 3: Unreachable Endpoint", "FAIL"))

    # Final Summary Table
    print("\n" + "="*45)
    print("FINAL SUMMARY")
    print("="*45)
    for test_name, status in summary:
        print(f"{test_name:35} | {status}")
    print("="*45)

if __name__ == "__main__":
    asyncio.run(main())
