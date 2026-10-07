import pytest

from app.services.summarizer.chunking import chunk_text


def test_empty_text_returns_no_chunks() -> None:
    assert chunk_text("") == []
    assert chunk_text(" \n\t ") == []


def test_text_shorter_than_limit_is_returned_trimmed() -> None:
    assert chunk_text(" \nShort text.  ", max_chars=30, overlap=3) == ["Short text."]


def test_text_at_exact_limit_is_single_chunk() -> None:
    text = "x" * 20

    assert chunk_text(text, max_chars=20, overlap=4) == [text]


def test_long_text_is_split_at_word_boundaries_and_respects_limit() -> None:
    text = "alpha bravo charlie delta echo foxtrot golf hotel"

    chunks = chunk_text(text, max_chars=18, overlap=0)

    assert len(chunks) > 1
    assert all(len(chunk) <= 18 for chunk in chunks)
    assert " ".join(chunks).replace("  ", " ") == text


def test_chunks_overlap_without_losing_text() -> None:
    text = "abcdefghij"

    chunks = chunk_text(text, max_chars=4, overlap=1)

    assert chunks == ["abcd", "defg", "ghij"]
    rebuilt = chunks[0] + "".join(chunk[1:] for chunk in chunks[1:])
    assert rebuilt == text


@pytest.mark.parametrize(
    ("text", "limit", "overlap", "message"),
    [
        ("text", 0, 0, "max_chars"),
        ("text", -2, 0, "max_chars"),
        ("text", 5, -1, "overlap"),
        ("text", 5, 5, "overlap"),
    ],
)
def test_invalid_chunk_configuration_raises(
    text: str,
    limit: int,
    overlap: int,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        chunk_text(text, max_chars=limit, overlap=overlap)


def test_rejects_overlap_larger_than_chunk_size() -> None:
    with pytest.raises(ValueError, match="overlap"):
        chunk_text("text", max_chars=3, overlap=4)
