import os
import time
import json
import logging
import asyncio
import httpx

try:
    from core.config import settings
    VLM_ENDPOINT = getattr(settings, "VLM_ENDPOINT", os.environ.get("VLM_ENDPOINT", "http://localhost:8001"))
except ImportError:
    VLM_ENDPOINT = os.environ.get("VLM_ENDPOINT", "http://localhost:8001")

logger = logging.getLogger(__name__)

MODEL_NAME = "Qwen/Qwen2.5-VL-3B-Instruct-AWQ"

class VLMClientError(Exception):
    pass

class VLMClient:
    def __init__(self):
        self.endpoint = VLM_ENDPOINT
        self.timeout = 60.0
        self.max_retries = 3

    async def health_check(self) -> bool:
        """GETs /v1/models to check if vLLM is up."""
        url = f"{self.endpoint}/v1/models"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url)
                return response.status_code == 200
        except Exception as e:
            logger.info(f"Health check failed: {e}")
            return False

    async def _post_with_retry(self, client: httpx.AsyncClient, method_name: str, payload: dict) -> dict:
        url = f"{self.endpoint}/v1/chat/completions"
        backoff = 1
        
        for attempt in range(1, self.max_retries + 1):
            start_time = time.time()
            try:
                response = await client.post(url, json=payload)
                
                # If 4xx, do not retry
                if 400 <= response.status_code < 500:
                    response.raise_for_status()

                # If 5xx, raise to trigger retry
                if response.status_code >= 500:
                    response.raise_for_status()
                    
                response_data = response.json()
                duration = time.time() - start_time
                usage = response_data.get("usage", {})
                
                logger.info(
                    f"{method_name} - Latency: {duration:.2f}s - "
                    f"Tokens: {usage.get('prompt_tokens', 0)} prompt, "
                    f"{usage.get('completion_tokens', 0)} completion, "
                    f"{usage.get('total_tokens', 0)} total (Attempt {attempt})"
                )
                
                return response_data

            except (httpx.TimeoutException, httpx.HTTPStatusError) as e:
                # Retry on timeout or 5xx
                if isinstance(e, httpx.HTTPStatusError) and 400 <= e.response.status_code < 500:
                    logger.error(f"{method_name} failed with 4xx error: {e}")
                    raise VLMClientError(f"Client error during {method_name}: {e}") from e
                
                if attempt == self.max_retries:
                    logger.error(f"Max retries reached for {method_name}.")
                    raise VLMClientError(f"Failed to complete {method_name} after {attempt} attempts: {e}") from e
                
                logger.warning(f"{method_name} failed (attempt {attempt}): {e}. Retrying in {backoff}s...")
                await asyncio.sleep(backoff)
                backoff *= 2
            except Exception as e:
                # Catch-all for other unexpected exceptions (e.g. connection error)
                if attempt == self.max_retries:
                    raise VLMClientError(f"Failed to complete {method_name}: {e}") from e
                logger.warning(f"{method_name} error (attempt {attempt}): {e}. Retrying in {backoff}s...")
                await asyncio.sleep(backoff)
                backoff *= 2
                
    def _strip_markdown_fences(self, text: str) -> str:
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            if len(lines) >= 2 and lines[-1].strip() == "```":
                text = "\n".join(lines[1:-1])
        return text.strip()

    async def classify(self, image_b64: str, mime_type: str = "image/png") -> dict:
        system_prompt = (
            'You are a document classification expert. Classify the document image into one of these types:\n'
            '- "invoice": Any commercial invoice, supplier invoice, purchase invoice, tax invoice, or sales invoice. '
            'This includes supplier invoices with part numbers, component listings, order tables, itemized charges, '
            'shipping details, and payment terms. Common suppliers include electronics distributors (Mouser, Digi-Key, '
            'RS Components, Arrow), manufacturers, and any vendor billing for goods or services. '
            'Key indicators: invoice number, date, supplier name, bill-to/ship-to address, line items with quantities '
            'and prices, subtotal, taxes (GST, VAT, CGST, SGST), and total amount due.\n'
            '- "bill_of_entry": A customs document filed for imported goods. '
            'Key indicators: BE number, port of entry, importer details, HS codes, assessed value, customs duty.\n'
            '- "unknown": Use only if the document clearly does not match either type above.\n\n'
            'Return ONLY valid JSON with no explanation: {"document_type": "invoice", "confidence": 0.95}'
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{image_b64}"}}
                ]
            }
        ]
        
        payload = {
            "model": MODEL_NAME,
            "messages": messages,
            "temperature": 0.1,
            "max_tokens": 256
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response_data = await self._post_with_retry(client, "classify", payload)
            
        content = response_data["choices"][0]["message"]["content"]
        cleaned_content = self._strip_markdown_fences(content)
        
        try:
            return json.loads(cleaned_content)
        except json.JSONDecodeError as e:
            raise VLMClientError(f"Failed to parse classification JSON. Raw response: {content}") from e

    async def extract(self, image_b64: str, prompt: str, schema: str, mime_type: str = "image/png") -> str:
        system_prompt = "You are a strict data extraction system. Return ONLY valid JSON."
        
        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{image_b64}"}}
                ]
            }
        ]
        
        payload = {
            "model": MODEL_NAME,
            "messages": messages,
            "temperature": 0.1,
            # Deliberately conservative because max_model_len is only 4096 total and the image encoder budget 
            # can consume most of it. This should be tuned upward only after confirming real prompt-token counts.
            "max_tokens": 1024 
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response_data = await self._post_with_retry(client, "extract", payload)
            
        return response_data["choices"][0]["message"]["content"]
