from typing import Optional
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "Document Extraction API"
    SLM_ENDPOINT: str
    SLM_MODEL: str = "qwen2.5:3b"
    SLM_API_KEY: Optional[str] = None

settings = Settings()
