from pathlib import Path

import chardet

from app.services.extractors.base import ExtractedDocument, Extractor, TextSegment, combine_segments


class _PlainTextExtractor(Extractor):
    def marker(self) -> str:
        raise NotImplementedError

    def extract(self, path: Path) -> ExtractedDocument:
        raw = path.read_bytes()
        detected = chardet.detect(raw)
        encoding = detected.get("encoding") or "utf-8"
        try:
            text = raw.decode(encoding)
        except (LookupError, UnicodeDecodeError):
            text = raw.decode("utf-8", errors="replace")
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        segment = TextSegment(marker=self.marker(), text=text.strip())
        return ExtractedDocument(
            text=combine_segments([segment]),
            page_count=1 if text.strip() else 0,
            segments=[segment],
        )


class TextFileExtractor(_PlainTextExtractor):
    def marker(self) -> str:
        return "Document"


class MarkdownExtractor(_PlainTextExtractor):
    def marker(self) -> str:
        return "Markdown document"
