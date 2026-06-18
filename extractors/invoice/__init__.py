import json
import re
from pydantic import ValidationError
from models.vlm_client import VLMClient
from schemas.invoice import InvoiceSchema
from core.exceptions import ExtractionError
from extractors.prompts.invoice_prompt import INVOICE_EXTRACTION_PROMPT

class InvoiceExtractor:
    def __init__(self, vlm_client: VLMClient):
        self.vlm_client = vlm_client

    async def extract(self, image_b64: str) -> InvoiceSchema:
        try:
            raw = await self.vlm_client.extract(image_b64, INVOICE_EXTRACTION_PROMPT, InvoiceSchema.model_json_schema())
            cleaned = re.sub(r'```(?:json)?\s*|\s*```', '', raw).strip()
            parsed = json.loads(cleaned)
            return InvoiceSchema(**parsed)
        except (json.JSONDecodeError, ValidationError) as e:
            raise ExtractionError(f"JSON parse failed: {e}")
