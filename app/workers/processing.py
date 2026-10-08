import logging
import tempfile
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.core.supabase import get_supabase
from app.schemas.documents import SummaryStyle
from app.services.extractors import get_extractor
from app.services.summarizer import summarize_text

logger = logging.getLogger(__name__)


def update_document(document_id: str, changes: dict[str, Any]) -> None:
    get_supabase().table("documents").update(changes).eq("id", document_id).execute()


def mark_document_failed(document_id: str, task_id: str, exc: BaseException) -> None:
    message = "Document processing failed. Please retry or upload the document again."
    if isinstance(exc, (ValueError, RuntimeError)):
        message = str(exc)[:1000]
    update_document(document_id, {"status": "failed", "error_message": message})
    logger.error(
        "Document processing failed",
        extra={"document_id": document_id, "task_id": task_id, "event": "document_failed"},
        exc_info=(type(exc), exc, exc.__traceback__),
    )


def process_document(document_id: str, style: str, task_id: str) -> None:
    client = get_supabase()
    document_result = (
        client.table("documents")
        .select("id,user_id,filename,file_type,file_size,storage_path,extracted_text")
        .eq("id", document_id)
        .single()
        .execute()
    )
    document = document_result.data
    if not document:
        raise ValueError("The requested document no longer exists.")

    existing_summary = (
        client.table("summaries")
        .select("id")
        .eq("processing_task_id", task_id)
        .maybe_single()
        .execute()
    )
    if existing_summary is not None and existing_summary.data:
        update_document(document_id, {"status": "completed", "error_message": None})
        return

    extracted_text = document.get("extracted_text")
    if not extracted_text:
        update_document(document_id, {"status": "extracting", "error_message": None})
        file_content = client.storage.from_(get_settings().storage_bucket).download(document["storage_path"])
        if len(file_content) != document.get("file_size"):
            raise ValueError("The uploaded file size does not match its document record.")
        with tempfile.TemporaryDirectory(prefix="docubrief-") as temporary_directory:
            local_path = Path(temporary_directory) / Path(document["filename"]).name
            local_path.write_bytes(file_content)
            extracted = get_extractor(document["file_type"]).extract(local_path)
        extracted_text = extracted.text
        if not extracted_text.strip():
            raise ValueError("No readable text was found in this document.")
        update_document(
            document_id,
            {
                "extracted_text": extracted_text,
                "page_count": extracted.page_count,
                "status": "summarizing",
            },
        )
    else:
        update_document(document_id, {"status": "summarizing", "error_message": None})

    summary = summarize_text(extracted_text, SummaryStyle(style))
    client.table("summaries").insert(
        {
            "document_id": document_id,
            "processing_task_id": task_id,
            "style": style,
            "title": summary.title,
            "summary_text": summary.summary_text,
            "key_points": summary.key_points,
            "model_used": summary.model_used,
            "token_count": summary.token_count,
        }
    ).execute()
    update_document(document_id, {"status": "completed", "error_message": None})
    logger.info(
        "Document processing completed",
        extra={"document_id": document_id, "task_id": task_id, "event": "document_completed"},
    )
