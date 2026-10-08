import asyncio
import logging
import uuid
from pathlib import PurePosixPath
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import ValidationError

from app.core.auth import UserClaims
from app.core.config import get_settings
from app.core.rate_limit import enforce_rate_limit
from app.core.supabase import get_supabase
from app.schemas.documents import (
    DocumentAccepted,
    DocumentDetail,
    DocumentListResponse,
    DocumentResponse,
    DocumentStatus,
    RegenerateSummaryRequest,
    RegenerateSummaryResponse,
    SummaryResponse,
    UploadDocumentRequest,
    UploadFailureRequest,
    UploadPreparationResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/documents", tags=["documents"])
ALLOWED_TYPES = {"pdf", "docx", "pptx", "txt", "md"}


def _enqueue_document(document_id: str, style: str) -> None:
    if get_settings().is_vercel:
        from vercel.queue import send

        asyncio.run(send("documents", {"document_id": document_id, "style": style}))
        return

    from app.workers.tasks import process_document_task

    process_document_task.apply_async(args=[document_id, style], queue="documents")


def _storage_object_path(user_id: str, document_id: str, file_type: str) -> str:
    return f"{user_id}/{document_id}/document.{file_type}"


def _document_or_404(
    document_id: str,
    user_id: str,
    *,
    include_text: bool = False,
) -> dict[str, Any]:
    columns = "id,user_id,filename,file_type,file_size,storage_path,status,error_message,page_count,created_at,updated_at"
    if include_text:
        columns += ",extracted_text"
    result = (
        get_supabase()
        .table("documents")
        .select(columns)
        .eq("id", document_id)
        .eq("user_id", user_id)
        .maybe_single()
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Document not found.")
    return result.data


def _parse_summary(data: dict[str, Any] | None) -> SummaryResponse | None:
    if data is None:
        return None
    try:
        return SummaryResponse.model_validate(data)
    except ValidationError as exc:
        logger.exception("Invalid summary record returned from database")
        raise HTTPException(status_code=500, detail="Could not read summary data.") from exc


@router.post("", response_model=UploadPreparationResponse, status_code=status.HTTP_202_ACCEPTED)
def upload_document(
    claims: UserClaims,
    body: UploadDocumentRequest,
) -> UploadPreparationResponse:
    user_id = claims["sub"]
    enforce_rate_limit(user_id=user_id, action="upload", limit=get_settings().upload_rate_limit)
    filename = PurePosixPath(body.filename.replace("\\", "/")).name.strip()
    if not filename or "." not in filename:
        raise HTTPException(status_code=400, detail="The uploaded file must have a supported extension.")
    file_type = filename.rsplit(".", 1)[-1].lower()
    if file_type not in ALLOWED_TYPES or file_type != body.file_type:
        raise HTTPException(status_code=415, detail="Supported formats are PDF, DOCX, PPTX, TXT, and MD.")

    document_id = str(uuid.uuid4())
    storage_path = _storage_object_path(user_id, document_id, file_type)
    supabase = get_supabase()
    row = {
        "id": document_id,
        "user_id": user_id,
        "filename": filename,
        "file_type": file_type,
        "file_size": body.file_size,
        "storage_path": storage_path,
        "status": "queued",
    }
    try:
        supabase.table("documents").insert(row).execute()
        signed_upload = supabase.storage.from_(get_settings().storage_bucket).create_signed_upload_url(
            storage_path
        )
    except Exception as exc:
        logger.exception(
            "Could not prepare document upload",
            extra={"document_id": document_id, "user_id": user_id, "event": "upload_prepare_failed"},
        )
        try:
            supabase.table("documents").delete().eq("id", document_id).eq("user_id", user_id).execute()
        except Exception:
            logger.exception(
                "Could not clean up document after upload preparation failed",
                extra={"document_id": document_id, "user_id": user_id, "event": "upload_prepare_cleanup_failed"},
            )
        raise HTTPException(status_code=503, detail="The upload could not be prepared. Please try again.") from exc
    return UploadPreparationResponse(
        id=uuid.UUID(document_id),
        status=DocumentStatus.QUEUED,
        storage_path=storage_path,
        upload_url=signed_upload["signed_url"],
    )


@router.post(
    "/{document_id}/process",
    response_model=DocumentAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
def queue_document_processing(document_id: uuid.UUID, claims: UserClaims) -> DocumentAccepted:
    user_id = claims["sub"]
    row = _document_or_404(str(document_id), user_id)
    if row["status"] != DocumentStatus.QUEUED.value:
        raise HTTPException(status_code=409, detail="This document is not waiting for processing.")
    try:
        _enqueue_document(str(document_id), "Brief")
    except Exception as exc:
        logger.exception(
            "Could not enqueue uploaded document",
            extra={"document_id": str(document_id), "user_id": user_id, "event": "enqueue_failed"},
        )
        get_supabase().table("documents").update(
            {"status": "failed", "error_message": "The document could not be queued. Please try again."}
        ).eq("id", str(document_id)).eq("user_id", user_id).execute()
        raise HTTPException(status_code=503, detail="The document could not be queued. Please try again.") from exc
    return DocumentAccepted(id=document_id, status=DocumentStatus.QUEUED)


@router.post("/{document_id}/upload-failed", status_code=status.HTTP_204_NO_CONTENT)
def mark_upload_failed(
    document_id: uuid.UUID,
    body: UploadFailureRequest,
    claims: UserClaims,
) -> None:
    row = _document_or_404(str(document_id), claims["sub"])
    if row["status"] == DocumentStatus.QUEUED.value:
        get_supabase().table("documents").update(
            {"status": "failed", "error_message": body.message}
        ).eq("id", str(document_id)).eq("user_id", claims["sub"]).execute()


@router.get("", response_model=DocumentListResponse)
def list_documents(claims: UserClaims, limit: int = 50, offset: int = 0) -> DocumentListResponse:
    if not 1 <= limit <= 100 or offset < 0:
        raise HTTPException(status_code=422, detail="limit must be 1-100 and offset must be non-negative.")
    result = (
        get_supabase()
        .table("documents")
        .select(
            "id,filename,file_type,file_size,status,error_message,page_count,created_at,updated_at",
            count="exact",
        )
        .eq("user_id", claims["sub"])
        .order("created_at", desc=True)
        .range(offset, offset + limit - 1)
        .execute()
    )
    rows = result.data or []
    ids = [row["id"] for row in rows]
    latest_by_document: dict[str, dict[str, Any]] = {}
    if ids:
        summaries_result = (
            get_supabase()
            .table("summaries")
            .select("*")
            .in_("document_id", ids)
            .order("created_at", desc=True)
            .execute()
        )
        for summary in summaries_result.data or []:
            latest_by_document.setdefault(summary["document_id"], summary)
    documents = [
        DocumentResponse.model_validate(
            {**row, "summary": _parse_summary(latest_by_document.get(row["id"]))}
        )
        for row in rows
    ]
    return DocumentListResponse(documents=documents, total=result.count or 0)


@router.get("/{document_id}", response_model=DocumentDetail)
def get_document(document_id: uuid.UUID, claims: UserClaims) -> DocumentDetail:
    row = _document_or_404(str(document_id), claims["sub"], include_text=True)
    summaries_result = (
        get_supabase()
        .table("summaries")
        .select("*")
        .eq("document_id", str(document_id))
        .order("created_at", desc=True)
        .execute()
    )
    summaries = [SummaryResponse.model_validate(item) for item in (summaries_result.data or [])]
    summary = summaries[0] if summaries else None
    return DocumentDetail(
        **{key: value for key, value in row.items() if key != "extracted_text"},
        extracted_text=row.get("extracted_text"),
        summary=summary,
        summaries=summaries,
    )


@router.get("/{document_id}/status", response_model=DocumentResponse)
def get_document_status(document_id: uuid.UUID, claims: UserClaims) -> DocumentResponse:
    row = _document_or_404(str(document_id), claims["sub"])
    summary_result = (
        get_supabase()
        .table("summaries")
        .select("*")
        .eq("document_id", str(document_id))
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    row["summary"] = _parse_summary((summary_result.data or [None])[0])
    return DocumentResponse.model_validate(row)


@router.post("/{document_id}/summaries", response_model=RegenerateSummaryResponse, status_code=202)
def regenerate_summary(
    document_id: uuid.UUID,
    body: RegenerateSummaryRequest,
    claims: UserClaims,
) -> RegenerateSummaryResponse:
    user_id = claims["sub"]
    enforce_rate_limit(user_id=user_id, action="summarize", limit=get_settings().summarize_rate_limit)
    row = _document_or_404(str(document_id), user_id, include_text=True)
    if not row.get("extracted_text"):
        raise HTTPException(status_code=409, detail="Text extraction must complete before regenerating a summary.")
    get_supabase().table("documents").update(
        {"status": "summarizing", "error_message": None}
    ).eq("id", str(document_id)).eq("user_id", user_id).execute()
    try:
        _enqueue_document(str(document_id), body.style.value)
    except Exception as exc:
        logger.exception(
            "Could not queue summary regeneration",
            extra={"document_id": str(document_id), "user_id": user_id, "event": "regenerate_failed"},
        )
        get_supabase().table("documents").update(
            {"status": "completed", "error_message": "Summary regeneration could not be queued."}
        ).eq("id", str(document_id)).eq("user_id", user_id).execute()
        raise HTTPException(status_code=503, detail="Summary regeneration could not be queued.") from exc
    return RegenerateSummaryResponse(id=document_id, status=DocumentStatus.SUMMARIZING)
