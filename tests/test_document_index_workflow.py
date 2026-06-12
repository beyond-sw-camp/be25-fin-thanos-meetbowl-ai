import asyncio
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.core.errors import AiError
from app.ports.embedding import EmbeddingRequest, EmbeddingResult
from app.ports.vector_store import ReplaceDocumentRequest
from app.schemas.indexing import AccessScope, DocumentMetadata, IndexDocumentCommand
from app.workflows.document_indexing import DocumentIndexingWorkflow


class CapturingEmbeddingProvider:
    def __init__(self) -> None:
        self.requests: list[EmbeddingRequest] = []

    async def embed(self, request: EmbeddingRequest) -> EmbeddingResult:
        self.requests.append(request)
        embeddings = [
            [0.1 + index, 0.2 + index, 0.3 + index]
            for index, _ in enumerate(request.texts)
        ]
        return EmbeddingResult(
            embeddings=embeddings,
            model_name="fake-embedding-model",
            dimensions=3,
        )


class CapturingVectorStore:
    def __init__(self) -> None:
        self.requests: list[ReplaceDocumentRequest] = []

    async def replace_document(self, request: ReplaceDocumentRequest) -> None:
        self.requests.append(request)


def command() -> IndexDocumentCommand:
    return IndexDocumentCommand(
        document_id=uuid4(),
        document_type="MEETING_MINUTES",
        organization_id=uuid4(),
        owner_user_id=uuid4(),
        title="주간 배포 회의록",
        content=(
            "첫 문단입니다. 배포 일정과 검증 범위를 정리했습니다.\n\n"
            "둘째 문단입니다. 롤백 조건과 모니터링 지표를 확인했습니다."
        ),
        access_scope=AccessScope(user_ids=[uuid4()]),
        metadata=DocumentMetadata(
            meeting_id=uuid4(),
            approved_at=datetime(2026, 6, 12, tzinfo=timezone.utc),
        ),
        created_at=datetime(2026, 6, 12, tzinfo=timezone.utc),
    )


def test_document_indexing_workflow_embeds_and_replaces_document() -> None:
    index_command = command()
    embedding_provider = CapturingEmbeddingProvider()
    vector_store = CapturingVectorStore()
    workflow = DocumentIndexingWorkflow(
        embedding_port=embedding_provider,
        vector_store_port=vector_store,
        model_profile="document-embedding",
        chunk_size=40,
        chunk_overlap=8,
        chunk_strategy_version="paragraph-v1",
    )

    result = asyncio.run(workflow.execute(index_command))

    assert result.chunk_count >= 2
    assert result.embedding_model == "fake-embedding-model"
    assert embedding_provider.requests[0].model_profile == "document-embedding"
    assert len(vector_store.requests) == 1
    stored = vector_store.requests[0]
    assert stored.document_id == str(result.document_id)
    assert stored.vector_size == 3
    assert stored.points[0].payload["sourceType"] == "MEETING_MINUTES"
    assert stored.points[0].payload["chunkStrategyVersion"] == "paragraph-v1"
    assert stored.points[0].payload["allowedUserIds"]
    assert stored.points[0].payload["content"].startswith("첫 문단입니다.")
    assert stored.points[0].payload["metadata"]["meetingId"] == str(
        index_command.metadata.meeting_id
    )


def test_document_indexing_workflow_rejects_empty_access_scope() -> None:
    workflow = DocumentIndexingWorkflow(
        embedding_port=CapturingEmbeddingProvider(),
        vector_store_port=CapturingVectorStore(),
        model_profile="document-embedding",
        chunk_size=40,
        chunk_overlap=8,
        chunk_strategy_version="paragraph-v1",
    )
    invalid = command().model_copy(update={"access_scope": AccessScope()})

    with pytest.raises(AiError, match="열람 범위가 비어"):
        asyncio.run(workflow.execute(invalid))
