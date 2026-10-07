from app.core.config import get_settings


def chunk_text(
    text: str,
    *,
    max_chars: int | None = None,
    overlap: int | None = None,
) -> list[str]:
    limit = get_settings().llm_chunk_chars if max_chars is None else max_chars
    overlap_size = get_settings().llm_chunk_overlap if overlap is None else overlap
    if limit <= 0:
        raise ValueError("max_chars must be greater than zero.")
    if overlap_size < 0 or overlap_size >= limit:
        raise ValueError("overlap must be non-negative and smaller than max_chars.")
    cleaned = text.strip()
    if not cleaned:
        return []
    if len(cleaned) <= limit:
        return [cleaned]

    chunks: list[str] = []
    start = 0
    while start < len(cleaned):
        end = min(start + limit, len(cleaned))
        if end < len(cleaned):
            boundary = cleaned.rfind("\n", start, end)
            if boundary <= start:
                boundary = cleaned.rfind(" ", start, end)
            if boundary > start:
                end = boundary
        chunk = cleaned[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(cleaned):
            break
        next_start = max(start + 1, end - overlap_size)
        start = next_start
    return chunks
