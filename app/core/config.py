from functools import lru_cache

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "DocuBrief API"
    environment: str = "development"
    vercel: bool = False
    cors_origins: str = "http://localhost:3000"
    supabase_url: str = ""
    supabase_anon_key: SecretStr = SecretStr("")
    supabase_service_role_key: SecretStr = SecretStr("")
    redis_url: str = "redis://redis:6379/0"
    celery_broker_url: str | None = None
    celery_result_backend: str | None = None
    storage_bucket: str = "documents"
    max_upload_bytes: int = 25 * 1024 * 1024
    jwt_audience: str = "authenticated"
    llm_api_key: SecretStr = SecretStr("")
    llm_base_url: str | None = None
    llm_model: str = "gpt-4o-mini"
    llm_chunk_chars: int = 12_000
    llm_chunk_overlap: int = 500
    pdf_ocr_mode: str | None = None
    upload_rate_limit: int = Field(default=10, ge=1)
    summarize_rate_limit: int = Field(default=10, ge=1)
    rate_limit_window_seconds: int = Field(default=3600, ge=1)
    log_level: str = "INFO"

    @field_validator("pdf_ocr_mode")
    @classmethod
    def validate_pdf_ocr_mode(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.lower()
        if normalized not in {"tesseract", "llm"}:
            raise ValueError("PDF_OCR_MODE must be 'tesseract' or 'llm'.")
        return normalized

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def is_vercel(self) -> bool:
        return self.vercel or self.environment.lower() == "vercel"

    @property
    def effective_pdf_ocr_mode(self) -> str:
        return self.pdf_ocr_mode or ("llm" if self.is_vercel else "tesseract")


@lru_cache
def get_settings() -> Settings:
    return Settings()
