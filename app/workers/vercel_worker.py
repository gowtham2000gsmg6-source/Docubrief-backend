from app.celery_app import celery_app as app
from app.workers import tasks as _registered_tasks

__all__ = ["app"]
