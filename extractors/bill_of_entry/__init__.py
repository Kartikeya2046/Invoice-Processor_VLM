import json
import re
from pydantic import ValidationError
from models.vlm_client import VLMClient
from schemas.bill_of_entry import BOESchema
from core.exceptions import ExtractionError
from extractors.prompts.boe_prompt import BOE_EXTRACTION_PROMPT

class BOEExtractor:
    def __init__(self, vlm_client: VLMClient):
        self.vlm_client = vlm_client

    async def extract(self, image_b64: str) -> BOESchema:
        try:
            raw = await self.vlm_client.extract(image_b64, BOE_EXTRACTION_PROMPT, BOESchema.model_json_schema())
            cleaned = re.sub(r'```(?:json)?\s*|\s*```', '', raw).strip()
            parsed = json.loads(cleaned)
            return BOESchema(**parsed)
        except (json.JSONDecodeError, ValidationError) as e:
            raise ExtractionError(f"JSON parse failed: {e}")
