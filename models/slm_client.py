import httpx
import asyncio
import logging
import json
import time
from typing import Optional

from core.config import settings
from core.exceptions import SLMUnavailableError

logger = logging.getLogger(__name__)

class SLMClient:
    def __init__(self):
        self.endpoint = settings.SLM_ENDPOINT
        self.model = settings.SLM_MODEL
        self.api_key = settings.SLM_API_KEY
        self.max_retries = 3

    async def validate(self, extracted_json: dict, document_type: str, prompt: str) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": prompt},
                {"role": "user", "content": json.dumps(extracted_json)}
            ],
            "stream": False,
            "options": {
                "temperature": 0.1
            }
        }

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        url = f"{self.endpoint.rstrip('/')}/api/chat"
        backoff = 1

        for attempt in range(1, self.max_retries + 1):
            start_time = time.time()
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.post(url, json=payload, headers=headers)
                    response.raise_for_status()

                    data = response.json()
                    content = data["message"]["content"]

                    latency = time.time() - start_time
                    prompt_tokens = data.get("prompt_eval_count", 0)
                    completion_tokens = data.get("eval_count", 0)

                    logger.info(f"validate - Latency: {latency:.2f}s - Tokens: {prompt_tokens} prompt, {completion_tokens} completion (Attempt {attempt})")

                    return content

            except (httpx.ConnectTimeout, httpx.ConnectError, httpx.ReadTimeout) as e:
                if attempt == self.max_retries:
                    raise SLMUnavailableError(f"SLM endpoint unreachable after 3 attempts: {self.endpoint}") from e
                logger.warning(f"SLM validate error (attempt {attempt}): {e}. Retrying in {backoff}s...")
                await asyncio.sleep(backoff)
                backoff *= 2
