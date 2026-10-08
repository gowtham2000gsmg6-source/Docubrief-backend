from app.api.routes.documents import _storage_object_path


def test_storage_object_path_does_not_include_user_filename() -> None:
    path = _storage_object_path(
        "68685135-fa58-43b4-abc1-8a72d667c0ca",
        "f533b4e4-1e7d-4248-a3c6-1e88c58d27b3",
        "pdf",
    )

    assert path == (
        "68685135-fa58-43b4-abc1-8a72d667c0ca/"
        "f533b4e4-1e7d-4248-a3c6-1e88c58d27b3/document.pdf"
    )
    assert "Campus Visitor Tracking System" not in path


def test_storage_object_path_preserves_supported_extension() -> None:
    assert _storage_object_path("user-id", "document-id", "docx").endswith("/document.docx")
