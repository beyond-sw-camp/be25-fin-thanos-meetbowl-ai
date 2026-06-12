from typing import Any

import httpx
from pydantic import ValidationError

from app.core.errors import ProviderUnavailableError
from app.rag.access_filter import build_chat_access_filter
from app.rag.sparse import SparseEncoder
from app.schemas.chat import ChatCommand, ChatSource

# 융합 전 각 검색 경로(dense/sparse)에서 모을 후보 수. 최종 limit보다 넉넉히 잡아 recall을 확보한다.
_CANDIDATE_LIMIT = 50
_FINAL_LIMIT = 10


class QdrantChatRetriever:
    """dense(의미)와 sparse(BM25) 검색을 RRF로 융합하는 하이브리드 검색 adapter."""

    def __init__(
        self,
        *,
        qdrant_url: str,
        qdrant_collection: str,
        http_client: httpx.AsyncClient | None = None,
        sparse_encoder: SparseEncoder | None = None,
    ) -> None:
        self._qdrant_url = qdrant_url.rstrip("/")
        self._qdrant_collection = qdrant_collection
        self._http_client = http_client
        self._sparse_encoder = sparse_encoder or SparseEncoder()

    async def search(
        self,
        *,
        vector: list[float],
        query: str,
        command: ChatCommand,
        source_types: list[str] | None = None,
        limit: int = _FINAL_LIMIT,
    ) -> list[ChatSource]:
        """dense 벡터와 query의 sparse 벡터로 하이브리드 검색 후 출처 목록을 반환한다.

        `source_types`로 자료 유형을 좁힐 수 있고, `limit`은 융합 후 반환 수(재정렬 후보 pool)다.
        """
        # 권한 조건은 두 검색 경로 모두에 적용해 융합 결과에도 열람 범위가 유지되게 한다.
        access_filter = build_chat_access_filter(command, source_types=source_types)
        sparse_vector = self._sparse_encoder.encode(query)
        # 각 경로 후보는 최종 limit 이상으로 잡아 융합 품질을 확보한다.
        candidate_limit = max(_CANDIDATE_LIMIT, limit)
        body = {
            "prefetch": [
                {
                    "query": vector,
                    "using": "dense",
                    "filter": access_filter,
                    "limit": candidate_limit,
                },
                {
                    "query": sparse_vector,
                    "using": "sparse",
                    "filter": access_filter,
                    "limit": candidate_limit,
                },
            ],
            # 두 경로의 순위를 Reciprocal Rank Fusion으로 합쳐 최종 순위를 만든다.
            "query": {"fusion": "rrf"},
            "limit": limit,
            "with_payload": True,
        }
        try:
            client = self._http_client or httpx.AsyncClient(timeout=10.0)
            response = await client.post(
                f"{self._qdrant_url}/collections/{self._qdrant_collection}/points/query",
                json=body,
            )
            response.raise_for_status()
            result = response.json().get("result", {})
            points = result.get("points", result if isinstance(result, list) else [])
            return self._to_sources(points)
        except Exception as exc:
            raise ProviderUnavailableError("Qdrant 검색에 실패했습니다.") from exc
        finally:
            if self._http_client is None and "client" in locals():
                await client.aclose()

    def _to_sources(self, points: list[dict[str, Any]]) -> list[ChatSource]:
        """Qdrant 검색 결과(point)를 챗봇 출처(ChatSource) 모델로 변환한다."""
        sources: list[ChatSource] = []
        for point in points:
            payload = point.get("payload") or {}
            # payload 형식이 깨진 항목은 건너뛰어 부분 실패에도 검색이 동작하게 한다.
            try:
                snippet = payload.get("snippet") or payload.get("content")
                sources.append(
                    ChatSource(
                        type=payload["sourceType"],
                        resource_id=payload.get("sourceId") or payload["documentId"],
                        title=payload["title"],
                        snippet=snippet,
                        score=max(0.0, min(1.0, float(point.get("score", 0.0)))),
                    )
                )
            except (KeyError, TypeError, ValueError, ValidationError):
                continue
        return sources
