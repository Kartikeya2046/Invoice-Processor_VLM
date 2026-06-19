import os
import sys
import asyncio
import json

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from models.slm_client import SLMClient
from validators.slm_validator import SLMValidator
from validators.invoice_validator import validate_invoice_rules
from validators.boe_validator import validate_boe_rules
from validators.confidence_scorer import merge_validation_results
from schemas.invoice import InvoiceSchema
from schemas.bill_of_entry import BOESchema

def model_to_dict(model):
    return model.model_dump(mode='json')

async def main():
    print("--- FULL VALIDATION PIPELINE CHECK ---")
    summary = []

    slm_client = SLMClient()
    slm_validator = SLMValidator(slm_client)

    # Test 1: Known-good invoice
    print("\n--- Test 1: Known-good invoice (expect clean pass) ---")
    try:
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
        rule_results = validate_invoice_rules(invoice)
        invoice_dict = model_to_dict(invoice)
        slm_results = await slm_validator.validate(invoice_dict, "invoice")
        
        merged_result = merge_validation_results(rule_results, slm_results, "invoice")
        
        for f in merged_result.fields:
            print(f"  Field: {f.field_name:15} | Conf: {f.confidence:.1f} | Flag: {f.flag}")
            
        print(f"\n  Overall Confidence: {merged_result.overall_confidence:.2f}")
        print(f"  Requires Review: {merged_result.requires_review}")
        print(f"  SLM Unavailable: {merged_result.slm_validation_unavailable}")
        
        if not merged_result.requires_review:
            print("PASS: requires_review is False")
            summary.append(("Test 1: Known-good invoice", "PASS"))
        else:
            print("FAIL: requires_review is True")
            summary.append(("Test 1: Known-good invoice", "FAIL"))
            
    except Exception as e:
        print(f"FAIL: Exception raised: {e}")
        summary.append(("Test 1: Known-good invoice", "FAIL"))


    # Test 2: Known-bad BOE
    print("\n--- Test 2: Known-bad BOE (expect requires_review=True) ---")
    try:
        boe_bad = BOESchema(
            boe_number="7842531",
            boe_date="2024-03-14",
            igst=69588.0,
            cust_duty=35145.0,
            sbcess=35145.0
        )
        rule_results_bad = validate_boe_rules(boe_bad)
        boe_bad_dict = model_to_dict(boe_bad)
        slm_results_bad = await slm_validator.validate(boe_bad_dict, "bill_of_entry")
        
        merged_result_bad = merge_validation_results(rule_results_bad, slm_results_bad, "bill_of_entry")
        
        for f in merged_result_bad.fields:
            print(f"  Field: {f.field_name:15} | Conf: {f.confidence:.1f} | Flag: {f.flag}")
            
        print(f"\n  Overall Confidence: {merged_result_bad.overall_confidence:.2f}")
        print(f"  Requires Review: {merged_result_bad.requires_review}")
        print(f"  SLM Unavailable: {merged_result_bad.slm_validation_unavailable}")
        
        if merged_result_bad.requires_review:
            print("PASS: requires_review is True")
            summary.append(("Test 2: Known-bad BOE", "PASS"))
        else:
            print("FAIL: requires_review is False")
            summary.append(("Test 2: Known-bad BOE", "FAIL"))
            
    except Exception as e:
        print(f"FAIL: Exception raised: {e}")
        summary.append(("Test 2: Known-bad BOE", "FAIL"))


    # Test 3: Known-good BOE
    print("\n--- Test 3: Known-good BOE (expect clean pass) ---")
    try:
        boe_good = BOESchema(
            boe_number="7842531",
            boe_date="2024-03-14",
            igst=69588.0,
            cust_duty=35145.0,
            sbcess=3514.5
        )
        rule_results_good = validate_boe_rules(boe_good)
        boe_good_dict = model_to_dict(boe_good)
        slm_results_good = await slm_validator.validate(boe_good_dict, "bill_of_entry")
        
        merged_result_good = merge_validation_results(rule_results_good, slm_results_good, "bill_of_entry")
        
        for f in merged_result_good.fields:
            print(f"  Field: {f.field_name:15} | Conf: {f.confidence:.1f} | Flag: {f.flag}")
            
        print(f"\n  Overall Confidence: {merged_result_good.overall_confidence:.2f}")
        print(f"  Requires Review: {merged_result_good.requires_review}")
        print(f"  SLM Unavailable: {merged_result_good.slm_validation_unavailable}")
        
        if not merged_result_good.requires_review:
            print("PASS: requires_review is False")
            summary.append(("Test 3: Known-good BOE", "PASS"))
        else:
            print("FAIL: requires_review is True")
            summary.append(("Test 3: Known-good BOE", "FAIL"))
            
    except Exception as e:
        print(f"FAIL: Exception raised: {e}")
        summary.append(("Test 3: Known-good BOE", "FAIL"))


    print("\n" + "="*45)
    print("FINAL SUMMARY")
    print("="*45)
    for test_name, status in summary:
        print(f"{test_name:35} | {status}")
    print("="*45)

if __name__ == "__main__":
    asyncio.run(main())
