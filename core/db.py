import os
from core.config import settings

import asyncpg

def get_db_url():
    url = os.environ.get("DATABASE_URL", getattr(settings, 'DATABASE_URL', None))
    if not url:
        raise ValueError("DATABASE_URL is not configured in environment or settings")
    # asyncpg.connect requires standard postgresql://
    return url.replace("postgresql+asyncpg://", "postgresql://")

async def update_status_async(document_id: str, status: str, failed_stage: str = None, failure_reason: str = None):
    conn = await asyncpg.connect(get_db_url())
    try:
        if failed_stage:
            await conn.execute(
                "UPDATE documents SET status = $1, failed_stage = $2, failure_reason = $3, updated_at = NOW() WHERE id = $4",
                status, failed_stage, failure_reason, document_id
            )
        else:
            await conn.execute(
                "UPDATE documents SET status = $1, updated_at = NOW() WHERE id = $2",
                status, document_id
            )
    finally:
        await conn.close()
