from typing import List

from schemas.validation_result import ExtractionResult, FieldConfidence

def merge_validation_results(
    rule_results: List[FieldConfidence],
    slm_results: List[FieldConfidence],
    document_type: str
) -> ExtractionResult:
    
    auth_fields = {
        "invoice": {"invoice_date", "quantity", "unit_price", "cgst", "sgst", "invoice_number"},
        "bill_of_entry": {"boe_date", "igst", "cust_duty", "sbcess", "boe_number"}
    }.get(document_type, set())

    rule_dict = {res.field_name: res for res in rule_results}
    slm_dict = {res.field_name: res for res in slm_results}

    all_fields = set(rule_dict.keys()).union(slm_dict.keys())
    
    merged_fields = []
    
    for field_name in all_fields:
        rule_res = rule_dict.get(field_name)
        slm_res = slm_dict.get(field_name)
        
        if field_name in auth_fields and rule_res is not None:
            merged_fields.append(rule_res)
        elif rule_res is not None:
            if slm_res is not None:
                if slm_res.confidence < rule_res.confidence:
                    merged_fields.append(slm_res)
                else:
                    merged_fields.append(rule_res)
            else:
                merged_fields.append(rule_res)
        elif slm_res is not None:
            merged_fields.append(slm_res)

    if not merged_fields:
        overall_confidence = 0.0
    else:
        overall_confidence = sum(f.confidence for f in merged_fields) / len(merged_fields)

    requires_review = overall_confidence < 0.75 or any(f.confidence < 0.5 for f in merged_fields)
    slm_validation_unavailable = (len(slm_results) == 0)

    return ExtractionResult(
        document_type=document_type,
        fields=merged_fields,
        overall_confidence=overall_confidence,
        requires_review=requires_review,
        slm_validation_unavailable=slm_validation_unavailable
    )
