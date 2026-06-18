from datetime import datetime, timedelta, timezone
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
# 나열(scroll) 시 문서 청크까지 포함해 넉넉히 받아온 뒤 Python에서 문서 단위로 정리한다.
_SCROLL_FETCH_LIMIT = 500
_MIN_DATETIME = datetime.min.replace(tzinfo=timezone.utc)
# 사용자가 말하는 '오늘'은 한국 시간 기준이므로 날짜만 들어온 경계값을 KST 자정으로 해석한다.
_KST = timezone(timedelta(hours=9))


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

    async def list_by_owner(
        self,
        *,
        command: ChatCommand,
        created_after: str | None = None,
        created_before: str | None = None,
        source_types: list[str] | None = None,
        limit: int = 50,
    ) -> list[ChatSource]:
        """의미 검색 없이 권한 범위 내 자료를 최신순으로 나열한다(날짜 범위·유형으로 좁힘 가능).

        `created_after`~`created_before`(ISO 날짜/일시) 구간의 생성분만 반환하고, 같은 문서의
        여러 청크는 한 건으로 합친다. '오늘 만든 메모 전체', '6월 1일~10일 메일'처럼 나열형 질의에 쓴다.
        """
        points = await self._scroll_by_owner(command, source_types)
        documents = self._recent_documents(
            points, created_after=created_after, created_before=created_before
        )
        return documents[:limit]

    async def count_by_owner(
        self,
        *,
        command: ChatCommand,
        created_after: str | None = None,
        created_before: str | None = None,
        source_types: list[str] | None = None,
    ) -> int:
        """권한 범위 내 자료의 '문서 수'를 센다(청크가 아닌 문서 단위, 날짜 범위·유형으로 좁힘 가능)."""
        points = await self._scroll_by_owner(command, source_types)
        return len(
            self._recent_documents(
                points, created_after=created_after, created_before=created_before
            )
        )

    async def _scroll_by_owner(
        self, command: ChatCommand, source_types: list[str] | None
    ) -> list[dict[str, Any]]:
        """소유자/워크스페이스 권한 범위의 point를 벡터 없이 scroll로 가져온다(나열·집계 공용)."""
        # 검색과 동일한 소유자/워크스페이스 권한 필터를 그대로 적용한다.
        access_filter = build_chat_access_filter(command, source_types=source_types)
        body = {
            "filter": access_filter,
            "limit": _SCROLL_FETCH_LIMIT,
            "with_payload": True,
            "with_vector": False,
        }
        try:
            client = self._http_client or httpx.AsyncClient(timeout=10.0)
            response = await client.post(
                f"{self._qdrant_url}/collections/{self._qdrant_collection}/points/scroll",
                json=body,
            )
            response.raise_for_status()
            return response.json().get("result", {}).get("points", [])
        except Exception as exc:
            raise ProviderUnavailableError("Qdrant 조회에 실패했습니다.") from exc
        finally:
            if self._http_client is None and "client" in locals():
                await client.aclose()

    async def get_document(
        self, *, command: ChatCommand, resource_id: str, max_chars: int
    ) -> str:
        """권한 범위 내에서 한 문서의 모든 청크를 모아 본문 전체를 반환한다(전체 요약용).

        벡터 없이 documentId/sourceId로 scroll해 chunkIndex 순으로 이어 붙이고 max_chars로 상한을 둔다.
        권한 밖이거나 본문이 없으면 빈 문자열을 반환한다.
        """
        # 검색과 동일한 권한 필터에 더해, 지정한 문서의 청크만 추리는 조건을 추가한다.
        access_filter = build_chat_access_filter(command)
        access_filter["must"].append(
            {
                "should": [
                    {"key": "documentId", "match": {"value": str(resource_id)}},
                    {"key": "sourceId", "match": {"value": str(resource_id)}},
                ]
            }
        )
        body = {
            "filter": access_filter,
            "limit": _SCROLL_FETCH_LIMIT,
            "with_payload": True,
            "with_vector": False,
        }
        try:
            client = self._http_client or httpx.AsyncClient(timeout=10.0)
            response = await client.post(
                f"{self._qdrant_url}/collections/{self._qdrant_collection}/points/scroll",
                json=body,
            )
            response.raise_for_status()
            points = response.json().get("result", {}).get("points", [])
        except Exception as exc:
            raise ProviderUnavailableError("Qdrant 본문 조회에 실패했습니다.") from exc
        finally:
            if self._http_client is None and "client" in locals():
                await client.aclose()
        return _join_document_chunks(points, max_chars=max_chars)

    def _to_sources(self, points: list[dict[str, Any]]) -> list[ChatSource]:
        """Qdrant 검색 결과(point)를 챗봇 출처(ChatSource) 모델로 변환한다."""
        sources: list[ChatSource] = []
        for point in points:
            payload = point.get("payload") or {}
            source = self._payload_to_source(payload, point.get("score", 0.0))
            # payload 형식이 깨진 항목은 건너뛰어 부분 실패에도 검색이 동작하게 한다.
            if source is not None:
                sources.append(source)
        return sources

    def _recent_documents(
        self,
        points: list[dict[str, Any]],
        *,
        created_after: str | None,
        created_before: str | None,
    ) -> list[ChatSource]:
        """scroll 결과를 날짜 범위로 거른 뒤 최신순 정렬하고 문서 단위로 중복을 제거한다."""
        # 날짜만 들어온 경계값은 KST 기준으로 해석한다(payload의 createdAt은 UTC라 그대로 둔다).
        after = _parse_day_bound(created_after, end=False)
        before = _parse_day_bound(created_before, end=True)
        rows: list[tuple[datetime, ChatSource]] = []
        for point in points:
            payload = point.get("payload") or {}
            created = _parse_iso(payload.get("createdAt"))
            if after is not None and (created is None or created < after):
                continue
            if before is not None and (created is None or created >= before):
                continue
            # 나열은 관련도 점수가 의미 없으므로 1.0으로 채운다(스키마상 0~1 필요).
            source = self._payload_to_source(payload, 1.0)
            if source is not None:
                rows.append((created or _MIN_DATETIME, source))
        rows.sort(key=lambda row: row[0], reverse=True)
        documents: list[ChatSource] = []
        seen: set[Any] = set()
        for _, source in rows:
            if source.resource_id in seen:
                continue
            seen.add(source.resource_id)
            documents.append(source)
        return documents

    @staticmethod
    def _payload_to_source(payload: dict[str, Any], score: Any) -> ChatSource | None:
        """Qdrant payload 한 건을 ChatSource로 변환한다(형식 불량이면 None)."""
        try:
            snippet = payload.get("snippet") or payload.get("content")
            return ChatSource(
                type=payload["sourceType"],
                resource_id=payload.get("sourceId") or payload["documentId"],
                title=payload["title"],
                snippet=snippet,
                score=max(0.0, min(1.0, float(score))),
            )
        except (KeyError, TypeError, ValueError, ValidationError):
            return None


def _join_document_chunks(points: list[dict[str, Any]], *, max_chars: int) -> str:
    """문서 청크들을 chunkIndex 순으로 이어 붙이고 max_chars로 자른다(토큰 폭주 방지)."""

    def order(point: dict[str, Any]) -> int:
        try:
            return int((point.get("payload") or {}).get("chunkIndex", 0))
        except (TypeError, ValueError):
            return 0

    parts: list[str] = []
    for point in sorted(points, key=order):
        payload = point.get("payload") or {}
        text = payload.get("content") or payload.get("snippet")
        if text:
            parts.append(str(text))
    return "\n".join(parts).strip()[:max_chars]


def _parse_day_bound(value: Any, *, end: bool) -> datetime | None:
    """날짜 범위 경계값을 KST 기준 UTC datetime으로 해석한다(실패 시 None).

    날짜만 들어오면 KST 자정으로 보되, 끝 경계(`end=True`)는 그날 전체를 포함하도록
    다음 날 자정으로 올린다. 예) created_before='2026-06-10' → 6월 10일 전체 포함.
    """
    if not isinstance(value, str):
        return None
    bound = _parse_iso(value, assume_tz=_KST)
    if bound is None:
        return None
    if end and "T" not in value:
        bound = bound + timedelta(days=1)
    return bound


def _parse_iso(value: Any, *, assume_tz: timezone = timezone.utc) -> datetime | None:
    """ISO 8601 날짜/일시 문자열을 UTC datetime으로 파싱한다(실패 시 None).

    시간대가 없는 값(예: '2026-06-17')은 `assume_tz` 기준으로 해석한 뒤 UTC로 변환한다.
    """
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=assume_tz)
    return parsed.astimezone(timezone.utc)
