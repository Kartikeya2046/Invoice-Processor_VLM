from typing import Optional
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "Document Extraction API"
    API_KEY: str
    SLM_ENDPOINT: str
    SLM_MODEL: str = "qwen2.5:3b"
    SLM_API_KEY: Optional[str] = None
    
    CELERY_BROKER_URL: str = "redis://redis:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://redis:6379/1"
    WEBHOOK_MAX_RETRIES: int = 4
    WEBHOOK_RETRY_BACKOFF_BASE: float = 2.0
    WEBHOOK_TIMEOUT: float = 10.0

settings = Settings()
