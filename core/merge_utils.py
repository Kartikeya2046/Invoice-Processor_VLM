import datetime
from decimal import Decimal, InvalidOperation

def _normalize_value(val):
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return Decimal(str(val))
    if isinstance(val, datetime.date):
        return val
    
    if isinstance(val, str):
        val = val.strip()
        if not val:
            return None
            
        # Try Decimal
        try:
            return Decimal(val)
        except InvalidOperation:
            pass
            
        # Try Date
        try:
            return datetime.datetime.strptime(val, "%Y-%m-%d").date()
        except ValueError:
            pass
        try:
            return datetime.datetime.strptime(val, "%Y/%m/%d").date()
        except ValueError:
            pass
        try:
            return datetime.datetime.strptime(val, "%d-%m-%Y").date()
        except ValueError:
            pass
        try:
            return datetime.datetime.strptime(val, "%d/%m/%Y").date()
        except ValueError:
            pass
            
        # Fall back to lowercase string
        return val.lower()
        
    return val

def merge_page_extractions(page_results: list[dict], document_type: str) -> dict:
    """
    Returns: {
      "fields": {... scalars as values, lists as [{"page": N, "value": ...}] ...},
      "requires_review": bool,
      "conflicts": {"cust_duty": [{"page": 1, "value": "500"}, {"page": 3, "value": "550"}]}
    }
    """
    if document_type == "invoice":
        scalar_fields = ["invoice_number", "invoice_date", "supplier", "po_number", "cgst", "sgst"]
        list_fields = ["quantity", "unit_price"]
    elif document_type == "bill_of_entry":
        scalar_fields = ["boe_number", "boe_date", "igst", "cust_duty", "sbcess"]
        list_fields = []
    else:
        # Default fallback
        if not page_results:
            return {"fields": {}, "requires_review": False, "conflicts": {}}
        # Assume all fields are scalars
        scalar_fields = list(page_results[0]["extracted_fields"].keys())
        list_fields = []

    merged_fields = {}
    conflicts = {}
    requires_review = False

    # Process scalar fields
    for field in scalar_fields:
        normalized_values = {}  # Normalized -> first page it appeared
        raw_values = {}         # page -> raw value
        first_raw_val = None
        
        for result in page_results:
            page = result["page"]
            raw_val = result["extracted_fields"].get(field)
            if raw_val is not None and str(raw_val).strip() != "":
                raw_values[page] = raw_val
                
                norm_val = _normalize_value(raw_val)
                if norm_val is not None:
                    if norm_val not in normalized_values:
                        normalized_values[norm_val] = page
                        if first_raw_val is None:
                            first_raw_val = raw_val
                            
        if len(normalized_values) == 0:
            merged_fields[field] = None
        elif len(normalized_values) == 1:
            merged_fields[field] = first_raw_val
        else:
            merged_fields[field] = first_raw_val
            requires_review = True
            conflict_list = [{"page": p, "value": raw_values[p]} for p in raw_values]
            conflicts[field] = conflict_list

    # Process list fields
    for field in list_fields:
        collected = []
        for result in page_results:
            page = result["page"]
            raw_val = result["extracted_fields"].get(field)
            if raw_val is not None and str(raw_val).strip() != "":
                collected.append({"page": page, "value": raw_val})
        merged_fields[field] = collected

    # Process line_items (concatenate arrays)
    # ponytail: page-boundary row splitting not handled, see plan doc for upgrade path.
    merged_line_items = []
    for result in page_results:
        page_line_items = result["extracted_fields"].get("line_items", [])
        if isinstance(page_line_items, list):
            merged_line_items.extend(page_line_items)
    if merged_line_items:
        merged_fields["line_items"] = merged_line_items

    return {
        "fields": merged_fields,
        "requires_review": requires_review,
        "conflicts": conflicts
    }
