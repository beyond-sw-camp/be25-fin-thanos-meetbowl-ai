"""챗봇 검색용 sourceType 변환 검증."""

import asyncio
from datetime import datetime, timezone
from uuid import uuid4

from app.ports.embedding import EmbeddingRequest, EmbeddingResult
from app.ports.vector_store import ReplaceDocumentRequest
from app.schemas.indexing import AccessScope, IndexDocumentCommand
from app.workflows.document_indexing import DocumentIndexingWorkflow


class FakeEmbeddingPort:
    async def embed(self, request: EmbeddingRequest) -> EmbeddingResult:
        return EmbeddingResult(
            embeddings=[[0.0, 1.0, 2.0, 3.0] for _ in request.texts],
            model_name="fake-embedding",
            dimensions=4,
        )


class CapturingVectorStore:
    def __init__(self) -> None:
        self.request: ReplaceDocumentRequest | None = None

    async def replace_document(self, request: ReplaceDocumentRequest) -> None:
        self.request = request

    async def delete_document(self, document_id: str) -> None:
        pass


def test_meeting_minutes_is_indexed_as_chat_minutes_source_type() -> None:
    vector_store = CapturingVectorStore()
    workflow = DocumentIndexingWorkflow(
        embedding_port=FakeEmbeddingPort(),
        vector_store_port=vector_store,
        model_profile="document-embedding",
        chunk_size=1200,
        chunk_overlap=150,
        chunk_strategy_version="paragraph-v1",
    )
    command = IndexDocumentCommand(
        document_id=uuid4(),
        document_type="MEETING_MINUTES",
        organization_id=uuid4(),
        owner_user_id=uuid4(),
        title="회의록",
        content="회의록 본문",
        access_scope=AccessScope(user_ids=[uuid4()]),
        created_at=datetime.now(timezone.utc),
    )

    asyncio.run(workflow.execute(command))

    assert vector_store.request is not None
    assert vector_store.request.points[0].payload["sourceType"] == "MINUTES"
