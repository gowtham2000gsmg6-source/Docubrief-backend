from celery import Celery
from kombu import Queue

from app.core.config import get_settings

settings = get_settings()
broker_url = settings.celery_broker_url or settings.redis_url
result_backend = settings.celery_result_backend or settings.redis_url
celery_app = Celery(
    "docubrief",
    broker=broker_url,
    backend=result_backend,
    include=["app.workers.tasks"],
)
celery_app.conf.update(
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_track_started=True,
    result_expires=3600,
    task_default_queue="documents",
    task_queues=(Queue("documents"),),
    broker_connection_retry_on_startup=True,
)
