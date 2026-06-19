import json
import logging
import re
from typing import List

from models.slm_client import SLMClient
from core.exceptions import SLMUnavailableError
from schemas.validation_result import FieldConfidence
from extractors.prompts.slm_validation_prompt import SLM_VALIDATION_PROMPT

logger = logging.getLogger(__name__)

class SLMValidator:
    def __init__(self, slm_client: SLMClient):
        self.slm_client = slm_client

    async def validate(self, extracted_json: dict, document_type: str) -> List[FieldConfidence]:
        try:
            raw_response = await self.slm_client.validate(
                extracted_json=extracted_json,
                document_type=document_type,
                prompt=SLM_VALIDATION_PROMPT
            )
            
            # Strip markdown fences using the specified regex
            cleaned_response = re.sub(r'```(?:json)?\s*|\s*```', '', raw_response).strip()
            
            data = json.loads(cleaned_response)
            
            results = []
            for item in data:
                field_name = item.get("field_name")
                confidence = float(item.get("confidence", 0.0))
                flag = item.get("flag")
                
                # Fetch original value from input JSON if available
                value = extracted_json.get(field_name) if field_name else None
                
                if field_name:
                    results.append(FieldConfidence(
                        field_name=field_name,
                        value=value,
                        confidence=confidence,
                        flag=flag
                    ))
            return results
            
        except (json.JSONDecodeError, SLMUnavailableError) as e:
            logger.warning(f"SLM validation failed or parsing error: {e}")
            return []
        except Exception as e:
            logger.warning(f"Unexpected error in SLMValidator: {e}")
            return []
