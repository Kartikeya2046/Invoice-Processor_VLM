from datetime import date
from typing import Optional
from pydantic import BaseModel, ConfigDict

class LineItem(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    quantity: Optional[float] = None
    unit_price: Optional[float] = None

class InvoiceSchema(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    po_number: Optional[str] = None
    supplier: Optional[str] = None
    invoice_number: Optional[str] = None
    invoice_date: Optional[date] = None
    quantity: Optional[float] = None
    unit_price: Optional[float] = None
    cgst: Optional[float] = None
    sgst: Optional[float] = None
