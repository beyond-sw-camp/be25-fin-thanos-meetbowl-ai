from typing import Any
from uuid import UUID

import httpx

from app.core.errors import ProviderUnavailableError
from app.rag.feedback_access_filter import build_feedback_access_filter
from app.rag.sparse import SparseEncoder
from app.schemas.feedback import FeedbackCandidate, MeetingFeedbackCommand


class QdrantMeetingFeedbackRetriever:
    def __init__(
        self,
        *,
        qdrant_url: str,
        qdrant_collection: str,
        candidate_limit: int,
        http_client: httpx.AsyncClient | None = None,
        sparse_encoder: SparseEncoder | None = None,
    ) -> None:
        self._qdrant_url = qdrant_url.rstrip("/")
        self._qdrant_collection = qdrant_collection
        self._candidate_limit = candidate_limit
        self._http_client = http_client
        self._sparse_encoder = sparse_encoder or SparseEncoder()

    async def search(
        self,
        *,
        vector: list[float],
        query: str,
        command: MeetingFeedbackCommand,
    ) -> list[FeedbackCandidate]:
        access_filter = build_feedback_access_filter(
            command, exclude_meeting_id=str(command.meeting_id)
        )
        sparse_vector = self._sparse_encoder.encode(query)
        body = {
            "prefetch": [
                {
                    "query": vector,
                    "using": "dense",
                    "filter": access_filter,
                    "limit": self._candidate_limit,
                },
                {
                    "query": sparse_vector,
                    "using": "sparse",
                    "filter": access_filter,
                    "limit": self._candidate_limit,
                },
            ],
            "query": {"fusion": "rrf"},
            "limit": self._candidate_limit,
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
            return self._to_candidates(points)
        except Exception as exc:
            raise ProviderUnavailableError("Qdrant 피드백 검색에 실패했습니다.") from exc
        finally:
            if self._http_client is None and "client" in locals():
                await client.aclose()

    def _to_candidates(self, points: list[dict[str, Any]]) -> list[FeedbackCandidate]:
        candidates: list[FeedbackCandidate] = []
        for point in points:
            payload = point.get("payload") or {}
            metadata = payload.get("metadata") or {}
            source_id = payload.get("sourceId") or payload.get("documentId")
            if not source_id:
                continue
            approved_at = metadata.get("approvedAt")
            meeting_id = metadata.get("meetingId")
            try:
                candidates.append(
                    FeedbackCandidate(
                        minutes_id=UUID(str(source_id)),
                        meeting_id=UUID(str(meeting_id)) if meeting_id else None,
                        title=payload["title"],
                        meeting_date=(approved_at or "")[:10] or "unknown",
                        snippet=(payload.get("snippet") or payload.get("content") or "")[:2000],
                        score=max(0.0, min(1.0, float(point.get("score", 0.0)))),
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue
        return candidates
