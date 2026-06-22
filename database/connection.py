import os
from core.config import settings

def get_db_url():
    url = os.environ.get("DATABASE_URL", settings.DATABASE_URL if hasattr(settings, 'DATABASE_URL') else "postgresql+asyncpg://postgres:postgres@localhost:5432/docextract")
    # asyncpg.connect requires standard postgresql://
    return url.replace("postgresql+asyncpg://", "postgresql://")
