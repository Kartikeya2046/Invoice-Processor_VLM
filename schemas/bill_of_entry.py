from datetime import date
from typing import Optional
from pydantic import BaseModel, ConfigDict

class BOESchema(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    boe_number: Optional[str] = None
    boe_date: Optional[date] = None
    igst: Optional[float] = None
    cust_duty: Optional[float] = None
    sbcess: Optional[float] = None
