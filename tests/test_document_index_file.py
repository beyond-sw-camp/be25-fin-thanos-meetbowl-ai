"""드라이브 파일 색인 경로 검증: storage_key가 오면 S3에서 받아 추출한 텍스트로 색인한다."""

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from app.pipelines.file_text_extraction import FileTextExtractor
from app.schemas.indexing import AccessScope, IndexDocumentCommand
from app.workflows.document_indexing import DocumentIndexingWorkflow

FIXTURES = Path(__file__).parent / "fixtures" / "drive"


class FakeStorage:
    def __init__(self, data: bytes) -> None:
        self._data = data
        self.keys: list[str] = []

    async def download(self, storage_key: str) -> bytes:
        self.keys.append(storage_key)
        return self._data


class FakeGemini:
    async def extract_text(self, *, content: bytes, mime_type: str) -> str:
        return "GEMINI_FALLBACK"


def _workflow(storage: FakeStorage) -> DocumentIndexingWorkflow:
    return DocumentIndexingWorkflow(
        embedding_port=None,  # _resolve_content 검증에는 사용되지 않음
        vector_store_port=None,
        model_profile="document-embedding",
        chunk_size=1200,
        chunk_overlap=150,
        chunk_strategy_version="paragraph-v1",
        file_storage_port=storage,
        file_text_extractor=FileTextExtractor(gemini_extractor=FakeGemini()),
    )


def _command(**overrides) -> IndexDocumentCommand:
    base = dict(
        document_id=uuid4(),
        document_type="PERSONAL_DRIVE_FILE",
        owner_user_id=uuid4(),
        title="file",
        access_scope=AccessScope(user_ids=[uuid4()]),
        created_at=datetime.now(timezone.utc),
    )
    base.update(overrides)
    return IndexDocumentCommand(**base)


def test_drive_pdf_is_downloaded_from_s3_and_extracted() -> None:
    data = (FIXTURES / "sample1_weekly_sync_minutes.pdf").read_bytes()
    storage = FakeStorage(data)
    command = _command(
        storage_key="personal-drive/u/1",
        content_type="application/pdf",
        title="weekly.pdf",
    )

    text = asyncio.run(_workflow(storage)._resolve_content(command))

    assert "회의록" in text  # pypdf로 추출된 본문
    assert storage.keys == ["personal-drive/u/1"]  # S3에서 받아옴


def test_inline_content_skips_s3() -> None:
    storage = FakeStorage(b"")
    command = _command(content="직접 담은 본문", document_type="PERSONAL_MEMO")

    text = asyncio.run(_workflow(storage)._resolve_content(command))

    assert text == "직접 담은 본문"
    assert storage.keys == []  # content가 있으면 S3 다운로드 안 함
