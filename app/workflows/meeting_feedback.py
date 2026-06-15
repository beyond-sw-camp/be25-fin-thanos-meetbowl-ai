from datetime import datetime, timezone

from app.ports.embedding import EmbeddingPort, EmbeddingRequest
from app.rag.qdrant_feedback import QdrantMeetingFeedbackRetriever
from app.schemas.feedback import (
    FeedbackCandidate,
    MeetingFeedbackCommand,
    MeetingFeedbackResult,
)


class MeetingFeedbackWorkflow:
    def __init__(
        self,
        *,
        embedding_port: EmbeddingPort,
        retriever: QdrantMeetingFeedbackRetriever,
        query_model_profile: str,
        prompt_version: str,
        score_threshold: float,
    ) -> None:
        self._embedding_port = embedding_port
        self._retriever = retriever
        self._query_model_profile = query_model_profile
        self._prompt_version = prompt_version
        self._score_threshold = score_threshold

    async def execute(
        self, command: MeetingFeedbackCommand
    ) -> MeetingFeedbackResult | None:
        query = "\n".join(segment.text.strip() for segment in command.transcript_window).strip()
        if not query:
            return None
        embedding_result = await self._embedding_port.embed(
            EmbeddingRequest(
                texts=[query],
                model_profile=self._query_model_profile,
            )
        )
        candidates = await self._retriever.search(
            vector=embedding_result.embeddings[0],
            query=query,
            command=command,
        )
        candidates = [
            candidate
            for candidate in candidates
            if candidate.score >= self._score_threshold
        ]
        if not candidates:
            return None
        top_candidate = candidates[0]
        feedback_type = _classify_feedback_type(top_candidate.snippet)
        sources = candidates[: min(3, len(candidates))]
        message = _render_message(feedback_type, top_candidate)
        if not message:
            return None
        return MeetingFeedbackResult(
            meeting_id=command.meeting_id,
            feedback_type=feedback_type,
            message=message,
            sources=sources,
            model="rule-based-feedback",
            prompt_version=self._prompt_version,
            generated_at=datetime.now(timezone.utc),
        )


def _classify_feedback_type(snippet: str) -> str:
    normalized = snippet.lower()
    if any(keyword in normalized for keyword in ("완료", "해결", "조치 완료", "반영 완료")):
        return "RESOLVED_TOPIC"
    if any(keyword in normalized for keyword in ("결정", "확정", "진행하기로", "채택")):
        return "DECISION_REMINDER"
    return "DUPLICATE_DISCUSSION"


def _render_message(feedback_type: str, source: FeedbackCandidate) -> str:
    if feedback_type == "RESOLVED_TOPIC":
        return (
            f"유사한 이슈가 {source.meeting_date} 회의에서 이미 해결된 기록이 있습니다. "
            f"근거: {source.snippet}"
        )
    if feedback_type == "DECISION_REMINDER":
        return (
            f"이 안건은 {source.meeting_date} 회의에서 이미 결정된 이력이 있습니다. "
            f"근거: {source.snippet}"
        )
    return f"비슷한 논의가 {source.meeting_date} 회의록에 있습니다. 근거: {source.snippet}"
