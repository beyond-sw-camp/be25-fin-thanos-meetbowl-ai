import logging
import re
from datetime import datetime, timezone
from typing import Protocol
from uuid import uuid4

from app.ports.embedding import EmbeddingPort, EmbeddingRequest
from app.schemas.feedback import (
    FeedbackCandidate,
    FeedbackType,
    MeetingFeedbackCommand,
    MeetingFeedbackResult,
)

# Uvicorn 기본 로깅 설정에서도 실시간 피드백 처리 결과가 INFO 수준으로 보이게 한다.
logger = logging.getLogger("uvicorn.error")

_MAX_FEEDBACK_SOURCES = 2
_MAX_SOURCE_SNIPPET_LENGTH = 120


class MeetingFeedbackRetriever(Protocol):
    async def search(
        self,
        *,
        vector: list[float],
        query: str,
        command: MeetingFeedbackCommand,
    ) -> list[FeedbackCandidate]: ...


class MeetingFeedbackWorkflow:
    def __init__(
        self,
        *,
        embedding_port: EmbeddingPort,
        retriever: MeetingFeedbackRetriever,
        query_model_profile: str,
        score_threshold: float,
        allow_semantic_fallback: bool = False,
    ) -> None:
        self._embedding_port = embedding_port
        self._retriever = retriever
        self._query_model_profile = query_model_profile
        self._score_threshold = score_threshold
        self._allow_semantic_fallback = allow_semantic_fallback

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
        # 회의 원문은 로그에 남기지 않고 모델/차원만 기록해 실제 query embedding 호출을 관측한다.
        logger.info(
            "meeting feedback query embedded: meeting_id=%s session_id=%s "
            "model=%s dimensions=%s segments=%s chars=%s",
            command.meeting_id,
            command.session_id,
            embedding_result.model_name,
            embedding_result.dimensions,
            len(command.transcript_window),
            len(query),
        )
        candidates = await self._retriever.search(
            vector=embedding_result.embeddings[0],
            query=query,
            command=command,
        )
        if not candidates:
            logger.info(
                "meeting feedback skipped: no candidates meeting_id=%s session_id=%s",
                command.meeting_id,
                command.session_id,
            )
        qualified_candidates: list[tuple[FeedbackCandidate, FeedbackType]] = []
        for candidate in candidates:
            if candidate.score < self._score_threshold:
                continue
            feedback_type = _classify_feedback_type(query, candidate.snippet)
            if feedback_type is None and self._allow_semantic_fallback:
                feedback_type = "DUPLICATE_DISCUSSION"
            if feedback_type is not None:
                qualified_candidates.append((candidate, feedback_type))
        if not qualified_candidates:
            logger.info(
                "meeting feedback skipped: gate rejected candidates meeting_id=%s "
                "session_id=%s scores=%s threshold=%s semantic_fallback=%s",
                command.meeting_id,
                command.session_id,
                [round(candidate.score, 4) for candidate in candidates],
                self._score_threshold,
                self._allow_semantic_fallback,
            )
            return None
        top_candidate, feedback_type = qualified_candidates[0]
        # 검색·분류에는 원문 snippet을 사용하되 화면 전달 payload에는 짧은 근거만 포함한다.
        # 실시간 피드백은 회의 중 즉시 읽는 알림이므로 긴 회의록 본문을 그대로 싣지 않는다.
        sources = [
            _compact_source(candidate)
            for candidate, _ in qualified_candidates[:_MAX_FEEDBACK_SOURCES]
        ]
        message = _render_message(feedback_type, top_candidate)
        sequences = [segment.sequence for segment in command.transcript_window]
        return MeetingFeedbackResult(
            feedback_id=uuid4(),
            meeting_id=command.meeting_id,
            session_id=command.session_id,
            feedback_type=feedback_type,
            message=message,
            sources=sources,
            audience_user_ids=sorted(set(command.participant_user_ids), key=str),
            from_sequence=min(sequences),
            to_sequence=max(sequences),
            generated_at=datetime.now(timezone.utc),
        )


_TOKEN_PATTERN = re.compile(r"[0-9a-zA-Z가-힣]{2,}")
_STOP_WORDS = {
    "관련",
    "그리고",
    "대한",
    "대해",
    "논의",
    "문제",
    "이번",
    "이전",
    "오늘",
    "회의",
    "회의록",
    "합니다",
    "했습니다",
    "있습니다",
}


def _classify_feedback_type(query: str, snippet: str) -> FeedbackType | None:
    normalized = snippet.lower()
    if any(keyword in normalized for keyword in ("완료", "해결", "조치 완료", "반영 완료")):
        return "RESOLVED_TOPIC"
    if any(keyword in normalized for keyword in ("결정", "확정", "진행하기로", "채택")):
        return "DECISION_REMINDER"
    shared_terms = _meaningful_terms(query) & _meaningful_terms(snippet)
    if len(shared_terms) >= 2 or any(len(term) >= 4 for term in shared_terms):
        return "DUPLICATE_DISCUSSION"
    return None


def _meaningful_terms(text: str) -> set[str]:
    return {
        token
        for token in _TOKEN_PATTERN.findall(text.lower())
        if token not in _STOP_WORDS
    }


def _render_message(feedback_type: FeedbackType, source: FeedbackCandidate) -> str:
    if feedback_type == "RESOLVED_TOPIC":
        return f"{source.meeting_date} 회의에서 유사한 이슈가 이미 해결되었습니다."
    if feedback_type == "DECISION_REMINDER":
        return f"{source.meeting_date} 회의에서 이 안건이 이미 결정되었습니다."
    return f"{source.meeting_date} 회의에 비슷한 논의가 있습니다."


def _compact_source(candidate: FeedbackCandidate) -> FeedbackCandidate:
    return candidate.model_copy(
        update={"snippet": _truncate_text(candidate.snippet, _MAX_SOURCE_SNIPPET_LENGTH)}
    )


def _truncate_text(text: str, max_length: int) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= max_length:
        return normalized
    return f"{normalized[: max_length - 3]}..."
