from types import SimpleNamespace

from app.workers import processing


def test_process_document_continues_when_task_has_no_existing_summary(monkeypatch) -> None:
    document = {
        "id": "document-id",
        "user_id": "user-id",
        "filename": "report.txt",
        "file_type": "txt",
        "file_size": 4,
        "storage_path": "user-id/document-id/document.txt",
        "extracted_text": None,
    }
    updates: list[dict[str, object]] = []
    inserts: list[dict[str, object]] = []

    class Query:
        def __init__(self, table: str, operation: str = "select") -> None:
            self.table_name = table
            self.operation = operation

        def select(self, *_args, **_kwargs):
            self.operation = "select"
            return self

        def update(self, changes):
            self.operation = "update"
            updates.append(changes)
            return self

        def insert(self, row):
            self.operation = "insert"
            inserts.append(row)
            return self

        def eq(self, *_args):
            return self

        def single(self):
            return self

        def maybe_single(self):
            return self

        def execute(self):
            if self.table_name == "documents" and self.operation == "select":
                return SimpleNamespace(data=document)
            if self.table_name == "summaries" and self.operation == "select":
                return None
            return SimpleNamespace(data=None)

    class Storage:
        def from_(self, _bucket):
            return self

        def download(self, _path):
            return b"data"

    class Client:
        storage = Storage()

        def table(self, name):
            return Query(name)

    monkeypatch.setattr(processing, "get_supabase", lambda: Client())
    monkeypatch.setattr(
        processing,
        "get_settings",
        lambda: SimpleNamespace(storage_bucket="documents"),
    )
    monkeypatch.setattr(
        processing,
        "get_extractor",
        lambda _file_type: SimpleNamespace(
            extract=lambda _path: SimpleNamespace(text="Extracted text", page_count=1)
        ),
    )
    monkeypatch.setattr(
        processing,
        "summarize_text",
        lambda _text, _style: SimpleNamespace(
            title="Report",
            summary_text="Summary",
            key_points=["Point"],
            model_used="test-model",
            token_count=10,
        ),
    )

    processing.process_document("document-id", "Brief", "task-id")

    assert any(row.get("status") == "completed" for row in updates)
    assert len(inserts) == 1
    assert inserts[0]["processing_task_id"] == "task-id"
