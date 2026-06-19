import os
import sys

# Add the project root to sys.path so we can import schemas and validators
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from schemas.invoice import InvoiceSchema
from schemas.bill_of_entry import BOESchema
from validators.invoice_validator import validate_invoice_rules
from validators.boe_validator import validate_boe_rules

def main():
    print("--- RULE-BASED VALIDATOR CHECK ---")
    summary = []

    # Test 1: Good Invoice
    print("\n--- Test 1: Known-Good Invoice ---")
    invoice = InvoiceSchema(
        po_number=None,
        supplier="Ricci Microwave Co., Ltd.",
        invoice_number="R202209-12",
        invoice_date="2022-09-12",
        quantity=1000.0,
        unit_price=55.7,
        cgst=None,
        sgst=None
    )
    inv_results = validate_invoice_rules(invoice)
    inv_pass = True
    for res in inv_results:
        print(f"  Field: {res.field_name:15} | Conf: {res.confidence:.1f} | Flag: {res.flag}")
        if res.confidence < 0.7:
            inv_pass = False

    if inv_pass:
        print("PASS: All fields >= 0.7 confidence")
        summary.append(("Test 1: Known-Good Invoice", "PASS"))
    else:
        print("FAIL: Some fields had confidence < 0.7")
        summary.append(("Test 1: Known-Good Invoice", "FAIL"))

    # Test 2: Good BOE
    print("\n--- Test 2: Known-Good BOE ---")
    boe_good = BOESchema(
        boe_number="7842531",
        boe_date="2024-03-14",
        igst=69588.0,
        cust_duty=35145.0,
        sbcess=3514.5
    )
    boe_good_results = validate_boe_rules(boe_good)
    boe_good_pass = True
    for res in boe_good_results:
        print(f"  Field: {res.field_name:15} | Conf: {res.confidence:.1f} | Flag: {res.flag}")
        if res.confidence != 1.0:
            boe_good_pass = False

    if boe_good_pass:
        print("PASS: All fields == 1.0 confidence")
        summary.append(("Test 2: Known-Good BOE", "PASS"))
    else:
        print("FAIL: Not all fields had 1.0 confidence")
        summary.append(("Test 2: Known-Good BOE", "FAIL"))

    # Test 3: Bad BOE (SBCESS)
    print("\n--- Test 3: Known-Bad BOE (SBCESS range) ---")
    boe_bad = BOESchema(
        boe_number="7842531",
        boe_date="2024-03-14",
        igst=69588.0,
        cust_duty=35145.0,
        sbcess=35145.0
    )
    boe_bad_results = validate_boe_rules(boe_bad)
    boe_bad_pass = False
    for res in boe_bad_results:
        print(f"  Field: {res.field_name:15} | Conf: {res.confidence:.1f} | Flag: {res.flag}")
        if res.field_name == "sbcess" and res.confidence < 1.0 and res.flag is not None:
            boe_bad_pass = True

    if boe_bad_pass:
        print("PASS: sbcess correctly flagged")
        summary.append(("Test 3: Known-Bad BOE (SBCESS)", "PASS"))
    else:
        print("FAIL: sbcess not flagged properly")
        summary.append(("Test 3: Known-Bad BOE (SBCESS)", "FAIL"))

    # Final Summary Table
    print("\n" + "="*45)
    print("FINAL SUMMARY")
    print("="*45)
    for test_name, status in summary:
        print(f"{test_name:35} | {status}")
    print("="*45)

if __name__ == "__main__":
    main()
