from datetime import date
from typing import List
from schemas.invoice import InvoiceSchema
from schemas.validation_result import FieldConfidence

def validate_invoice_rules(invoice: InvoiceSchema) -> List[FieldConfidence]:
    results = []
    processed_fields = set()
    
    # invoice_date
    val = invoice.invoice_date
    processed_fields.add("invoice_date")
    if val is not None:
        if isinstance(val, date) and date(2000, 1, 1) <= val <= date.today():
            results.append(FieldConfidence(field_name="invoice_date", value=val, confidence=1.0))
        else:
            results.append(FieldConfidence(field_name="invoice_date", value=val, confidence=0.0, flag="invoice_date out of plausible range"))
    else:
        results.append(FieldConfidence(field_name="invoice_date", value=val, confidence=0.7, flag="field is null"))

    # quantity
    val = invoice.quantity
    processed_fields.add("quantity")
    if val is not None:
        if val > 0:
            results.append(FieldConfidence(field_name="quantity", value=val, confidence=1.0))
        else:
            results.append(FieldConfidence(field_name="quantity", value=val, confidence=0.0, flag="quantity must be positive"))
    else:
        results.append(FieldConfidence(field_name="quantity", value=val, confidence=1.0))

    # unit_price
    val = invoice.unit_price
    processed_fields.add("unit_price")
    if val is not None:
        if val > 0:
            results.append(FieldConfidence(field_name="unit_price", value=val, confidence=1.0))
        else:
            results.append(FieldConfidence(field_name="unit_price", value=val, confidence=0.0, flag="unit_price must be positive"))
    else:
        results.append(FieldConfidence(field_name="unit_price", value=val, confidence=1.0))

    # cgst / sgst
    processed_fields.add("cgst")
    processed_fields.add("sgst")
    cgst_val = invoice.cgst
    sgst_val = invoice.sgst
    if (cgst_val is None and sgst_val is None) or (cgst_val is not None and sgst_val is not None):
        results.append(FieldConfidence(field_name="cgst", value=cgst_val, confidence=1.0))
        results.append(FieldConfidence(field_name="sgst", value=sgst_val, confidence=1.0))
    else:
        results.append(FieldConfidence(field_name="cgst", value=cgst_val, confidence=0.5, flag="cgst/sgst should both be present or both absent"))
        results.append(FieldConfidence(field_name="sgst", value=sgst_val, confidence=0.5, flag="cgst/sgst should both be present or both absent"))

    # invoice_number
    val = invoice.invoice_number
    processed_fields.add("invoice_number")
    if val:
        results.append(FieldConfidence(field_name="invoice_number", value=val, confidence=1.0))
    else:
        results.append(FieldConfidence(field_name="invoice_number", value=val, confidence=0.0, flag="invoice_number is empty"))

    # All other fields
    for field_name, val in invoice.model_dump().items():
        if field_name not in processed_fields:
            if val is not None:
                results.append(FieldConfidence(field_name=field_name, value=val, confidence=1.0))
            else:
                results.append(FieldConfidence(field_name=field_name, value=val, confidence=0.7, flag="field is null"))

    return results
