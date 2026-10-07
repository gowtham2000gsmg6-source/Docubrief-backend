import base64
from io import BytesIO
from pathlib import Path

import fitz
import pytesseract
from openai import OpenAI
from PIL import Image

from app.core.config import get_settings
from app.services.extractors.base import ExtractedDocument, Extractor, TextSegment, combine_segments


def _layout_order(blocks: list[tuple]) -> list[str]:
    text_blocks = [
        block for block in blocks
        if len(block) >= 5 and isinstance(block[4], str) and block[4].strip()
    ]
    if len(text_blocks) < 4:
        return [block[4].strip() for block in sorted(text_blocks, key=lambda item: (item[1], item[0]))]

    page_width = max(float(block[2]) for block in text_blocks)
    centers = sorted((float(block[0]) + float(block[2])) / 2 for block in text_blocks)
    gaps = [(centers[index + 1] - centers[index], index) for index in range(len(centers) - 1)]
    gap, split_at = max(gaps, default=(0.0, 0))
    if gap < page_width * 0.12:
        return [block[4].strip() for block in sorted(text_blocks, key=lambda item: (item[1], item[0]))]
    split = (centers[split_at] + centers[split_at + 1]) / 2
    left = [block for block in text_blocks if (float(block[0]) + float(block[2])) / 2 < split]
    right = [block for block in text_blocks if (float(block[0]) + float(block[2])) / 2 >= split]
    left.sort(key=lambda item: (item[1], item[0]))
    right.sort(key=lambda item: (item[1], item[0]))
    return [block[4].strip() for block in [*left, *right]]


class PdfExtractor(Extractor):
    def __init__(self, *, ocr_min_characters: int = 1, ocr_language: str = "eng") -> None:
        self.ocr_min_characters = ocr_min_characters
        self.ocr_language = ocr_language

    def _ocr(self, image: Image.Image) -> str:
        settings = get_settings()
        if settings.effective_pdf_ocr_mode == "tesseract":
            return pytesseract.image_to_string(image, lang=self.ocr_language).strip()

        api_key = settings.llm_api_key.get_secret_value()
        if not api_key:
            raise RuntimeError("LLM_API_KEY must be configured for LLM-based PDF OCR.")
        image_buffer = BytesIO()
        image.save(image_buffer, format="PNG")
        image_data = base64.b64encode(image_buffer.getvalue()).decode("ascii")
        client_options: dict[str, str] = {"api_key": api_key}
        if settings.llm_base_url:
            client_options["base_url"] = settings.llm_base_url
        response = OpenAI(**client_options).chat.completions.create(
            model=settings.llm_model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Transcribe all readable text in this document page in reading order. Return only the transcription; do not summarize.",
                        },
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{image_data}"},
                        },
                    ],
                }
            ],
        )
        content = response.choices[0].message.content
        if not content:
            raise ValueError("The configured language model returned empty OCR text.")
        return content.strip()

    def extract(self, path: Path) -> ExtractedDocument:
        segments: list[TextSegment] = []
        with fitz.open(path) as document:
            for page_number, page in enumerate(document, start=1):
                text = "\n".join(_layout_order(page.get_text("blocks")))
                if len(text.strip()) < self.ocr_min_characters:
                    pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                    image = Image.frombytes("RGB", [pixmap.width, pixmap.height], pixmap.samples)
                    text = self._ocr(image)
                segments.append(TextSegment(marker=f"Page {page_number}", text=text))
            page_count = len(document)
        return ExtractedDocument(
            text=combine_segments(segments),
            page_count=page_count,
            segments=segments,
        )
