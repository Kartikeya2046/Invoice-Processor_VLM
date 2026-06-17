from pydantic import BaseModel, field_validator

class ClassificationResult(BaseModel):
    document_type: str
    confidence: float

    @field_validator("document_type")
    @classmethod
    def validate_document_type(cls, v: str) -> str:
        valid_types = {"invoice", "bill_of_entry", "unknown"}
        if v not in valid_types:
            raise ValueError(f"document_type must be one of {valid_types}, got '{v}'")
        return v

    @field_validator("confidence")
    @classmethod
    def validate_confidence(cls, v: float) -> float:
        if not (0.0 <= v <= 1.0):
            raise ValueError(f"confidence must be between 0.0 and 1.0, got {v}")
        return v
