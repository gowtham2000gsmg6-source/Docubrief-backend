from app.services.extractors.base import ExtractedDocument, Extractor, TextSegment
from app.services.extractors.docx import DocxExtractor
from app.services.extractors.pdf import PdfExtractor
from app.services.extractors.pptx import PptxExtractor
from app.services.extractors.text import MarkdownExtractor, TextFileExtractor

EXTRACTORS: dict[str, type[Extractor]] = {
    "pdf": PdfExtractor,
    "docx": DocxExtractor,
    "pptx": PptxExtractor,
    "txt": TextFileExtractor,
    "md": MarkdownExtractor,
}


def get_extractor(file_type: str) -> Extractor:
    extractor_type = EXTRACTORS.get(file_type.lower())
    if extractor_type is None:
        raise ValueError(f"Unsupported document type: {file_type}")
    return extractor_type()


__all__ = ["ExtractedDocument", "Extractor", "TextSegment", "get_extractor"]
