import uuid
from typing import Any
from uuid import UUID

import httpx

from app.core.errors import AiError, ProviderUnavailableError
from app.rag.sparse import SparseEncoder
from app.schemas.indexing import IndexDocumentCommand

# Qdrant payload(snippet)로 노출되는 청크 길이 상한. ChatSource.snippet(max 2000)을 넘지 않게 자른다.
_MAX_SNIPPET_CHARS = 1900

# 권한 필터·유형 필터·재색인 삭제에 쓰이는 payload 필드. 대용량에서 필터를 빠르게 하려고
# 컬렉션 생성 시 keyword 인덱스를 만든다(UUID/enum 문자열이라 모두 keyword).
_INDEXED_PAYLOAD_FIELDS = (
    "organizationId",
    "ownerUserId",
    "workspaceId",
    "sharedWorkspaceIds",
    "sourceType",
    "documentId",
)


class QdrantDocumentIndexer:
    """문서를 청크 단위 포인트로 Qdrant에 저장(upsert)하는 색인 adapter.

    하이브리드 검색을 위해 청크마다 dense(의미) 벡터와 sparse(BM25) 벡터를 함께 저장한다.
    """

    def __init__(
        self,
        *,
        qdrant_url: str,
        qdrant_collection: str,
        http_client: httpx.AsyncClient | None = None,
        sparse_encoder: SparseEncoder | None = None,
    ) -> None:
        self._qdrant_url = qdrant_url.rstrip("/")
        self.collection = qdrant_collection
        self._http_client = http_client
        self._sparse_encoder = sparse_encoder or SparseEncoder()

    async def upsert_document(
        self, *, command: IndexDocumentCommand, chunks: list[tuple[str, list[float]]]
    ) -> None:
        """문서를 청크 포인트들로 저장한다. 재색인 시 기존 청크를 먼저 제거해 잔여를 없앤다."""
        if not chunks:
            return
        client = self._http_client or httpx.AsyncClient(timeout=10.0)
        try:
            await self._ensure_collection(client, len(chunks[0][1]))
            # 문서가 더 적은 청크로 재색인될 때 이전 청크가 남지 않도록 먼저 삭제한다.
            await self._delete_existing(client, command.document_id)
            points = [
                self._build_point(command, index, text, vector)
                for index, (text, vector) in enumerate(chunks)
            ]
            response = await client.put(
                f"{self._qdrant_url}/collections/{self.collection}/points",
                params={"wait": "true"},
                json={"points": points},
            )
            response.raise_for_status()
        except AiError:
            raise
        except Exception as exc:
            raise ProviderUnavailableError("Qdrant 문서 색인에 실패했습니다.") from exc
        finally:
            if self._http_client is None:
                await client.aclose()

    def _build_point(
        self, command: IndexDocumentCommand, chunk_index: int, text: str, vector: list[float]
    ) -> dict[str, Any]:
        """청크 1개를 검색·권한 metadata가 포함된 Qdrant 포인트로 만든다."""
        # 챗봇 검색의 권한 필터와 동일한 키(조직/소유자/공유 워크스페이스)를 함께 저장한다.
        workspace_id = command.metadata.get("workspaceId")
        payload: dict[str, Any] = {
            "sourceType": command.source_type,
            "sourceId": str(command.document_id),
            "documentId": str(command.document_id),
            "organizationId": str(command.organization_id),
            "ownerUserId": str(command.owner_user_id),
            "sharedWorkspaceIds": [str(value) for value in command.shared_workspace_ids],
            "title": command.title,
            "content": text,
            "snippet": text[:_MAX_SNIPPET_CHARS],
            "chunkIndex": chunk_index,
            **command.metadata,
        }
        if workspace_id is not None:
            payload["workspaceId"] = str(workspace_id)
        return {
            # (문서 ID, 청크 번호)로 결정적 포인트 ID를 만들어 재색인 시 같은 청크를 덮어쓴다.
            "id": str(uuid.uuid5(command.document_id, str(chunk_index))),
            # dense(의미) 벡터와 sparse(BM25) 벡터를 named vector로 함께 저장한다.
            "vector": {
                "dense": vector,
                "sparse": self._sparse_encoder.encode(text),
            },
            "payload": payload,
        }

    async def _create_payload_indexes(self, client: httpx.AsyncClient) -> None:
        """권한·유형 필터 필드에 keyword payload 인덱스를 만들어 대용량 필터를 가속한다."""
        for field_name in _INDEXED_PAYLOAD_FIELDS:
            response = await client.put(
                f"{self._qdrant_url}/collections/{self.collection}/index",
                params={"wait": "true"},
                json={"field_name": field_name, "field_schema": "keyword"},
            )
            response.raise_for_status()

    async def _delete_existing(self, client: httpx.AsyncClient, document_id: UUID) -> None:
        """같은 문서의 기존 청크 포인트를 documentId 기준으로 모두 제거한다."""
        response = await client.post(
            f"{self._qdrant_url}/collections/{self.collection}/points/delete",
            params={"wait": "true"},
            json={
                "filter": {
                    "must": [{"key": "documentId", "match": {"value": str(document_id)}}]
                }
            },
        )
        response.raise_for_status()

    async def _ensure_collection(
        self, client: httpx.AsyncClient, vector_size: int
    ) -> None:
        """collection이 없으면 생성하고, 있으면 vector 차원이 일치하는지 검증한다."""
        response = await client.get(
            f"{self._qdrant_url}/collections/{self.collection}"
        )
        # collection이 아직 없으면 dense(명명) + sparse(BM25, IDF) 벡터 구성으로 새로 만든다.
        if response.status_code == 404:
            create_response = await client.put(
                f"{self._qdrant_url}/collections/{self.collection}",
                json={
                    "vectors": {"dense": {"size": vector_size, "distance": "Cosine"}},
                    # modifier=idf로 Qdrant가 질의 시점에 IDF를 적용해 BM25 점수를 낸다.
                    "sparse_vectors": {"sparse": {"modifier": "idf"}},
                },
            )
            create_response.raise_for_status()
            # 컬렉션을 새로 만든 직후 1회만 필터 필드 인덱스를 생성한다.
            await self._create_payload_indexes(client)
            return
        response.raise_for_status()
        # 이미 있는 collection이라면 임베딩 모델이 바뀌어 차원이 어긋나지 않았는지 확인한다.
        configured_size = response.json()["result"]["config"]["params"]["vectors"]["dense"]["size"]
        if configured_size != vector_size:
            raise AiError(
                "AI_DOCUMENT_INDEX_FAILED",
                "Qdrant collection의 vector 크기가 embedding model과 다릅니다.",
                status_code=500,
            )
