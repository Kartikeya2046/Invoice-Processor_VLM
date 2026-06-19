from datetime import date
from typing import List
from schemas.bill_of_entry import BOESchema
from schemas.validation_result import FieldConfidence

def validate_boe_rules(boe: BOESchema) -> List[FieldConfidence]:
    results = []
    processed_fields = set()

    # boe_date
    val = boe.boe_date
    processed_fields.add("boe_date")
    if val is not None:
        if isinstance(val, date) and date(2000, 1, 1) <= val <= date.today():
            results.append(FieldConfidence(field_name="boe_date", value=val, confidence=1.0))
        else:
            results.append(FieldConfidence(field_name="boe_date", value=val, confidence=0.0, flag="boe_date out of plausible range"))
    else:
        results.append(FieldConfidence(field_name="boe_date", value=val, confidence=0.7, flag="field is null"))

    # igst
    val = boe.igst
    processed_fields.add("igst")
    if val is None or val > 0:
        results.append(FieldConfidence(field_name="igst", value=val, confidence=1.0))
    else:
        results.append(FieldConfidence(field_name="igst", value=val, confidence=0.0, flag="igst must be positive"))

    # cust_duty
    val = boe.cust_duty
    processed_fields.add("cust_duty")
    if val is None or val > 0:
        results.append(FieldConfidence(field_name="cust_duty", value=val, confidence=1.0))
    else:
        results.append(FieldConfidence(field_name="cust_duty", value=val, confidence=0.0, flag="cust_duty must be positive"))

    # sbcess
    processed_fields.add("sbcess")
    val_sbcess = boe.sbcess
    val_cust = boe.cust_duty
    if val_sbcess is not None and val_cust is not None:
        if val_cust > 0 and (0.08 * val_cust) <= val_sbcess <= (0.12 * val_cust):
            results.append(FieldConfidence(field_name="sbcess", value=val_sbcess, confidence=1.0))
        else:
            results.append(FieldConfidence(field_name="sbcess", value=val_sbcess, confidence=0.4, flag="sbcess outside expected 8-12% range of cust_duty"))
    else:
        results.append(FieldConfidence(field_name="sbcess", value=val_sbcess, confidence=0.7, flag="insufficient data to cross-check sbcess"))

    # boe_number
    val = boe.boe_number
    processed_fields.add("boe_number")
    if val:
        results.append(FieldConfidence(field_name="boe_number", value=val, confidence=1.0))
    else:
        results.append(FieldConfidence(field_name="boe_number", value=val, confidence=0.0, flag="boe_number is empty"))

    # All other fields (if any)
    for field_name, val in boe.model_dump().items():
        if field_name not in processed_fields:
            if val is not None:
                results.append(FieldConfidence(field_name=field_name, value=val, confidence=1.0))
            else:
                results.append(FieldConfidence(field_name=field_name, value=val, confidence=0.7, flag="field is null"))

    return results
