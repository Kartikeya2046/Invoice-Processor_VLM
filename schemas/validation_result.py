from typing import Optional, Any, List
from pydantic import BaseModel

class FieldConfidence(BaseModel):
    field_name: str
    value: Optional[Any] = None
    confidence: float  # 0.0 to 1.0
    flag: Optional[str] = None

class ExtractionResult(BaseModel):
    document_type: str
    fields: List[FieldConfidence]
    overall_confidence: float
    requires_review: bool = False
    slm_validation_unavailable: bool = False
