INVOICE_EXTRACTION_PROMPT: str = """Extract these fields from the invoice image. Return ONLY valid JSON.

Fields and their aliases:
- po_number: PO Number, PO No, Purchase Order Number, Order No
- supplier: Supplier, Vendor, Seller, From, Sold By, Company Name
- invoice_number: Invoice No, Invoice #, Inv No, Bill No, Tax Invoice No
- invoice_date: Invoice Date, Bill Date, Date of Issue
- cgst: CGST, Central GST, Central Tax
- sgst: SGST, State GST, UTGST
- line_items: Extract every row of the product table into an array of line items.

Rules:
- line_items.description: item name or description
- line_items.product_code: product code, SKU, or part number
- line_items.quantity: return as plain number, strip commas and unit labels
- line_items.unit_price: return as plain number, strip currency symbols
- invoice_number: extract only the alphanumeric ID as printed, strip surrounding labels
- invoice_date: normalize to YYYY-MM-DD format
- cgst/sgst: return the amount value, not the percentage rate; return null if absent, never 0
- If a field is not present anywhere in the document, return null

Return a JSON object with this schema:
{
  "po_number": string | null,
  "supplier": string | null,
  "invoice_number": string | null,
  "invoice_date": "YYYY-MM-DD" | null,
  "cgst": number | null,
  "sgst": number | null,
  "line_items": [
    {
      "description": string | null,
      "product_code": string | null,
      "quantity": number | null,
      "unit_price": number | null
    }
  ]
}"""
