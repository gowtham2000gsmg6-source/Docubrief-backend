from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class TextSegment:
    marker: str
    text: str


@dataclass(frozen=True)
class ExtractedDocument:
    text: str
    page_count: int
    segments: list[TextSegment]


class Extractor(ABC):
    @abstractmethod
    def extract(self, path: Path) -> ExtractedDocument:
        raise NotImplementedError


def combine_segments(segments: list[TextSegment]) -> str:
    return "\n\n".join(f"[{segment.marker}]\n{segment.text.strip()}" for segment in segments if segment.text.strip())
