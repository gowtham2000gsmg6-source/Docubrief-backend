import asyncio
import logging
from typing import Any

from vercel.queue import Message, subscribe

from app.schemas.documents import SummaryStyle
from app.workers.processing import mark_document_failed, process_document

logger = logging.getLogger(__name__)


@subscribe(topic="documents")
async def process_document_message(message: Message[dict[str, Any]]) -> None:
    payload = message.payload
    document_id = payload.get("document_id")
    style = payload.get("style", SummaryStyle.BRIEF.value)
    if not isinstance(document_id, str) or not isinstance(style, str):
        raise ValueError("The queued document message is invalid.")

    try:
        SummaryStyle(style)
        await asyncio.to_thread(
            process_document,
            document_id,
            style,
            message.message_id,
        )
    except Exception as exc:
        try:
            mark_document_failed(document_id, message.message_id, exc)
        except Exception:
            logger.exception(
                "Could not persist document processing failure",
                extra={"document_id": document_id, "task_id": message.message_id, "event": "failure_persist_error"},
            )
        raise
