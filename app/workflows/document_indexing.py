from datetime import datetime, timezone
from uuid import NAMESPACE_URL, uuid5

from app.core.errors import AiError
from app.pipelines.chunking import split_document_into_chunks
from app.ports.embedding import EmbeddingPort, EmbeddingRequest
from app.ports.vector_store import ReplaceDocumentRequest, VectorPoint, VectorStorePort
from app.schemas.indexing import DocumentIndexingResult, IndexDocumentCommand


class DocumentIndexingWorkflow:
    def __init__(
        self,
        *,
        embedding_port: EmbeddingPort,
        vector_store_port: VectorStorePort,
        model_profile: str,
        chunk_size: int,
        chunk_overlap: int,
        chunk_strategy_version: str,
    ) -> None:
        self._embedding_port = embedding_port
        self._vector_store_port = vector_store_port
        self._model_profile = model_profile
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap
        self._chunk_strategy_version = chunk_strategy_version

    async def execute(self, command: IndexDocumentCommand) -> DocumentIndexingResult:
        content = command.content.strip()
        if not content:
            raise AiError(
                "AI_INVALID_EVENT",
                "색인할 문서 본문이 비어 있습니다.",
                status_code=400,
            )
        if command.access_scope.is_empty():
            raise AiError(
                "AI_RAG_ACCESS_DENIED",
                "색인 가능한 열람 범위가 비어 있습니다.",
                status_code=403,
            )

        chunks = split_document_into_chunks(
            title=command.title,
            content=content,
            max_chars=self._chunk_size,
            overlap_chars=self._chunk_overlap,
        )
        if not chunks:
            raise AiError(
                "AI_INVALID_EVENT",
                "색인할 문서 chunk를 만들 수 없습니다.",
                status_code=400,
            )

        # chunk 수와 임베딩 수가 어긋나면 어떤 본문이 어떤 벡터인지 매핑할 수 없으므로
        # 부분 성공으로 진행하지 않고 전체 요청을 재시도 대상으로 돌린다.
        embedding_result = await self._embedding_port.embed(
            EmbeddingRequest(
                texts=[chunk.embedding_text for chunk in chunks],
                model_profile=self._model_profile,
            )
        )
        if len(embedding_result.embeddings) != len(chunks):
            raise AiError(
                "AI_DOCUMENT_INDEX_FAILED",
                "임베딩 개수가 문서 chunk 개수와 일치하지 않습니다.",
                retryable=True,
                status_code=503,
            )

        # 같은 문서가 다시 들어와도 같은 chunk index와 전략 버전이면 같은 point id가 만들어진다.
        # 이벤트 중복 소비나 재색인 시 Qdrant upsert가 멱등하게 동작하도록 UUIDv5를 사용한다.
        points = [
            VectorPoint(
                point_id=str(
                    uuid5(
                        NAMESPACE_URL,
                        (
                            f"{command.document_id}:{chunk.chunk_index}:"
                            f"{self._chunk_strategy_version}"
                        ),
                    )
                ),
                vector=vector,
                payload={
                    "sourceType": command.document_type,
                    "sourceId": str(command.document_id),
                    "chunkIndex": chunk.chunk_index,
                    "chunkStrategyVersion": self._chunk_strategy_version,
                    "title": command.title,
                    "content": chunk.content,
                    "organizationId": str(command.organization_id),
                    "ownerUserId": str(command.owner_user_id),
                    "allowedUserIds": [
                        str(user_id) for user_id in command.access_scope.user_ids
                    ],
                    "allowedDepartmentIds": [
                        str(department_id)
                        for department_id in command.access_scope.department_ids
                    ],
                    "sharedWorkspaceIds": [
                        str(workspace_id)
                        for workspace_id in command.access_scope.shared_workspace_ids
                    ],
                    "metadata": command.metadata.model_dump(
                        mode="json", by_alias=True, exclude_none=True
                    ),
                    "createdAt": command.created_at.isoformat().replace("+00:00", "Z"),
                },
            )
            for chunk, vector in zip(chunks, embedding_result.embeddings, strict=True)
        ]
        # Qdrant에는 sourceId 단위로 기존 포인트를 먼저 지우고 새 포인트 집합으로 교체한다.
        # 본문 길이가 줄어든 재색인에서 오래된 chunk가 남는 문제를 막기 위한 전략이다.
        await self._vector_store_port.replace_document(
            ReplaceDocumentRequest(
                document_id=str(command.document_id),
                vector_size=embedding_result.dimensions,
                points=points,
            )
        )
        return DocumentIndexingResult(
            document_id=command.document_id,
            document_type=command.document_type,
            chunk_count=len(chunks),
            embedding_model=embedding_result.model_name,
            indexed_at=datetime.now(timezone.utc),
        )
