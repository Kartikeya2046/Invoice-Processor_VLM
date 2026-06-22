from celery import Celery
from core.config import settings

celery_app = Celery(
    'docextract',
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND
)

celery_app.conf.update(
    task_serializer='json',
    result_serializer='json',
    accept_content=['json'],
    task_track_started=True,
    worker_prefetch_multiplier=1,
)

# Explicitly import tasks instead of autodiscovery
from tasks import extract_task, validate_task, webhook_task
