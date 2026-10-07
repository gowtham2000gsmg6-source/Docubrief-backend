import logging
from typing import Any

from celery import Task
from celery.exceptions import SoftTimeLimitExceeded

from app.celery_app import celery_app
from app.workers.processing import mark_document_failed, process_document

logger = logging.getLogger(__name__)


class RetryingDocumentTask(Task):
    autoretry_for: tuple[type[BaseException], ...] = ()
    max_retries = 3
    soft_time_limit = 240
    time_limit = 270

    def on_failure(
        self,
        exc: BaseException,
        task_id: str,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        einfo: Any,
    ) -> None:
        document_id = str(args[0]) if args else "unknown"
        try:
            mark_document_failed(document_id, task_id, exc)
        except Exception:
            logger.exception(
                "Could not persist terminal document failure",
                extra={"document_id": document_id, "task_id": task_id, "event": "failure_persist_error"},
            )


@celery_app.task(
    bind=True,
    base=RetryingDocumentTask,
    name="documents.process",
    max_retries=3,
    soft_time_limit=240,
    time_limit=270,
)
def process_document_task(self: RetryingDocumentTask, document_id: str, style: str = "Brief") -> None:
    try:
        process_document(document_id, style, str(self.request.id))
    except SoftTimeLimitExceeded as exc:
        error = RuntimeError("Document processing exceeded its time limit.")
        retry_options = {"countdown": min(2 ** self.request.retries * 30, 600)}
        raise self.retry(exc=error, **retry_options) from exc
    except Exception as exc:
        retry_options = {"countdown": min(2 ** self.request.retries * 30, 600)}
        raise self.retry(exc=exc, **retry_options) from exc
