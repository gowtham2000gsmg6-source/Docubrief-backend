from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SummaryStyle(StrEnum):
    BRIEF = "Brief"
    DETAILED = "Detailed"
    BULLET_POINTS = "Bullet points"


class DocumentStatus(StrEnum):
    QUEUED = "queued"
    EXTRACTING = "extracting"
    SUMMARIZING = "summarizing"
    COMPLETED = "completed"
    FAILED = "failed"


class DocumentAccepted(BaseModel):
    id: UUID
    status: DocumentStatus


class UploadDocumentRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    file_type: str
    file_size: int = Field(gt=0, le=25 * 1024 * 1024)

    @field_validator("file_type")
    @classmethod
    def validate_file_type(cls, value: str) -> str:
        normalized = value.lower().lstrip(".")
        if normalized not in {"pdf", "docx", "pptx", "txt", "md"}:
            raise ValueError("Supported formats are PDF, DOCX, PPTX, TXT, and MD.")
        return normalized


class UploadPreparationResponse(BaseModel):
    id: UUID
    status: DocumentStatus
    storage_path: str
    upload_url: str


class UploadFailureRequest(BaseModel):
    message: str = Field(default="File upload did not complete.", max_length=500)


class SummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    document_id: UUID
    style: SummaryStyle
    title: str
    summary_text: str
    key_points: list[str]
    model_used: str
    token_count: int | None = None
    created_at: datetime


class DocumentResponse(BaseModel):
    id: UUID
    filename: str
    file_type: str
    file_size: int
    status: DocumentStatus
    error_message: str | None = None
    page_count: int | None = None
    created_at: datetime
    updated_at: datetime
    summary: SummaryResponse | None = None


class DocumentDetail(DocumentResponse):
    extracted_text: str | None = None
    summaries: list[SummaryResponse] = Field(default_factory=list)


class DocumentListResponse(BaseModel):
    documents: list[DocumentResponse]
    total: int


class RegenerateSummaryRequest(BaseModel):
    style: SummaryStyle = SummaryStyle.BRIEF


class RegenerateSummaryResponse(BaseModel):
    id: UUID
    status: DocumentStatus
