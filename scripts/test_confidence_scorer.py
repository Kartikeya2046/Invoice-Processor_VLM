import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from schemas.validation_result import FieldConfidence
from validators.confidence_scorer import merge_validation_results

def main():
    print("--- CONFIDENCE SCORER CHECK ---")
    summary = []

    # Test 1: Clean invoice, rule wins
    print("\n--- Test 1: Clean invoice, rule wins, no disagreement ---")
    fields = ["invoice_date", "quantity", "unit_price", "cgst", "sgst", "invoice_number", "supplier"]
    rule_results_1 = [FieldConfidence(field_name=f, confidence=1.0) for f in fields]
    rule_results_1.append(FieldConfidence(field_name="po_number", confidence=0.7, flag="field is null"))

    slm_results_1 = [FieldConfidence(field_name=f, confidence=1.0) for f in fields + ["po_number"]]
    # Override unit_price in SLM results
    for r in slm_results_1:
        if r.field_name == "unit_price":
            r.confidence = 0.3
            r.flag = "some bogus SLM concern"

    res_1 = merge_validation_results(rule_results_1, slm_results_1, "invoice")
    unit_price_conf = 0.0
    for f in res_1.fields:
        print(f"  Field: {f.field_name:15} | Conf: {f.confidence:.1f} | Flag: {f.flag}")
        if f.field_name == "unit_price":
            unit_price_conf = f.confidence
            
    if unit_price_conf == 1.0:
        print("PASS: unit_price correctly took rule confidence (1.0) and ignored SLM (0.3)")
        summary.append(("Test 1: Rule override", "PASS"))
    else:
        print(f"FAIL: unit_price has confidence {unit_price_conf}")
        summary.append(("Test 1: Rule override", "FAIL"))

    # Test 2: Non-rule field, conservative merge
    print("\n--- Test 2: Non-rule field, conservative merge ---")
    rule_results_2 = [FieldConfidence(field_name="supplier", confidence=1.0)]
    slm_results_2 = [FieldConfidence(field_name="supplier", confidence=0.4, flag="supplier name looks unusual")]
    res_2 = merge_validation_results(rule_results_2, slm_results_2, "invoice")
    supplier_conf = res_2.fields[0].confidence
    print(f"  Merged supplier: Conf={supplier_conf:.1f}, Flag={res_2.fields[0].flag}")
    if supplier_conf == 0.4:
        print("PASS: supplier took the lower conservative confidence (0.4)")
        summary.append(("Test 2: Conservative merge", "PASS"))
    else:
        print(f"FAIL: supplier confidence was {supplier_conf}")
        summary.append(("Test 2: Conservative merge", "FAIL"))

    # Test 3: requires_review triggers correctly
    print("\n--- Test 3: requires_review triggers correctly (BOE) ---")
    boe_fields = ["boe_date", "igst", "cust_duty", "boe_number"]
    rule_results_3 = [FieldConfidence(field_name=f, confidence=1.0) for f in boe_fields]
    rule_results_3.append(FieldConfidence(field_name="sbcess", confidence=0.3, flag="sbcess outside expected 8-12% range of cust_duty"))
    
    res_3 = merge_validation_results(rule_results_3, [], "bill_of_entry")
    print(f"  Requires Review: {res_3.requires_review}")
    print(f"  SLM Unavailable: {res_3.slm_validation_unavailable}")
    if res_3.requires_review and res_3.slm_validation_unavailable:
        print("PASS: Both flags correctly set to True")
        summary.append(("Test 3: requires_review True", "PASS"))
    else:
        print("FAIL: Flags not correctly set")
        summary.append(("Test 3: requires_review True", "FAIL"))

    # Test 4: Clean BOE, requires_review stays False
    print("\n--- Test 4: Clean BOE, requires_review stays False ---")
    rule_results_4 = [FieldConfidence(field_name=f, confidence=1.0) for f in boe_fields + ["sbcess"]]
    slm_results_4 = [FieldConfidence(field_name=f, confidence=1.0) for f in boe_fields + ["sbcess"]]
    res_4 = merge_validation_results(rule_results_4, slm_results_4, "bill_of_entry")
    print(f"  Requires Review: {res_4.requires_review}")
    print(f"  SLM Unavailable: {res_4.slm_validation_unavailable}")
    if not res_4.requires_review and not res_4.slm_validation_unavailable:
        print("PASS: Both flags correctly set to False")
        summary.append(("Test 4: requires_review False", "PASS"))
    else:
        print("FAIL: Flags incorrectly set to True")
        summary.append(("Test 4: requires_review False", "FAIL"))

    print("\n" + "="*45)
    print("FINAL SUMMARY")
    print("="*45)
    for test_name, status in summary:
        print(f"{test_name:35} | {status}")
    print("="*45)

if __name__ == "__main__":
    main()
