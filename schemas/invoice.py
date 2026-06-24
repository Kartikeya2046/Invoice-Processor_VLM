from datetime import date
from typing import Optional
from pydantic import BaseModel, ConfigDict

class LineItem(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    description: Optional[str] = None
    product_code: Optional[str] = None
    quantity: Optional[float] = None
    unit_price: Optional[float] = None

class InvoiceSchema(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    po_number: Optional[str] = None
    supplier: Optional[str] = None
    invoice_number: Optional[str] = None
    invoice_date: Optional[date] = None
    line_items: list[LineItem] = []
    # ponytail: dual-schema period, drop scalar fields once old rows confirmed unread.
    quantity: Optional[float | list] = None
    unit_price: Optional[float | list] = None
    cgst: Optional[float] = None
    sgst: Optional[float] = None
