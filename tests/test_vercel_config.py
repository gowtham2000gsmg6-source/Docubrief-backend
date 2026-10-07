import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_tesseract_is_default_outside_vercel() -> None:
    assert Settings().effective_pdf_ocr_mode == "tesseract"


def test_llm_ocr_is_default_on_vercel() -> None:
    assert Settings(vercel=True).effective_pdf_ocr_mode == "llm"


def test_explicit_pdf_ocr_mode_overrides_runtime_default() -> None:
    assert Settings(vercel=True, pdf_ocr_mode="tesseract").effective_pdf_ocr_mode == "tesseract"


def test_invalid_pdf_ocr_mode_is_rejected() -> None:
    with pytest.raises(ValidationError, match="PDF_OCR_MODE"):
        Settings(pdf_ocr_mode="unsupported")
