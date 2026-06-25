import asyncio
from uuid import UUID, uuid4

from app.ports.embedding import EmbeddingRequest, EmbeddingResult
from app.schemas.feedback import (
    FeedbackCandidate,
    FeedbackTranscriptSegment,
    MeetingFeedbackCommand,
)
from app.workflows.meeting_feedback import MeetingFeedbackWorkflow


class StubEmbeddingPort:
    def __init__(self) -> None:
        self.requests: list[EmbeddingRequest] = []

    async def embed(self, request: EmbeddingRequest) -> EmbeddingResult:
        self.requests.append(request)
        return EmbeddingResult(
            embeddings=[[0.1, 0.2]],
            model_name="stub-embedding",
            dimensions=2,
        )


class StubRetriever:
    def __init__(self, candidates: list[FeedbackCandidate]) -> None:
        self.candidates = candidates

    async def search(self, **_kwargs) -> list[FeedbackCandidate]:
        return self.candidates


def _candidate(*, snippet: str, score: float = 0.9) -> FeedbackCandidate:
    return FeedbackCandidate(
        minutes_id=uuid4(),
        meeting_id=uuid4(),
        title="과거 회의록",
        meeting_date="2026-06-10",
        snippet=snippet,
        score=score,
    )


def _command(
    *,
    texts: list[str] | None = None,
    participant_user_ids: list[UUID] | None = None,
) -> MeetingFeedbackCommand:
    texts = texts or ["결제 승인 정책을 다시 검토합니다", "자동 승인 기준을 조정합니다"]
    return MeetingFeedbackCommand(
        meeting_id=uuid4(),
        session_id=uuid4(),
        organization_id=uuid4(),
        participant_user_ids=participant_user_ids or [uuid4()],
        correlation_id=uuid4(),
        transcript_window=[
            FeedbackTranscriptSegment(
                segment_id=uuid4(),
                sequence=index + 10,
                language="ko",
                text=text,
                is_final=True,
                started_at_ms=index * 1_000,
                ended_at_ms=index * 1_000 + 500,
            )
            for index, text in enumerate(texts)
        ],
    )


def _workflow(
    candidates: list[FeedbackCandidate],
    *,
    score_threshold: float = 0.78,
    allow_semantic_fallback: bool = False,
) -> MeetingFeedbackWorkflow:
    return MeetingFeedbackWorkflow(
        embedding_port=StubEmbeddingPort(),
        retriever=StubRetriever(candidates),
        query_model_profile="query-embedding",
        score_threshold=score_threshold,
        allow_semantic_fallback=allow_semantic_fallback,
    )


def test_returns_none_when_search_has_no_candidates() -> None:
    result = asyncio.run(_workflow([]).execute(_command()))

    assert result is None


def test_returns_none_when_candidate_is_below_score_threshold() -> None:
    result = asyncio.run(
        _workflow([_candidate(snippet="결제 승인 정책 논의", score=0.77)]).execute(
            _command()
        )
    )

    assert result is None


def test_returns_none_when_candidate_has_no_explicit_evidence() -> None:
    result = asyncio.run(
        _workflow([_candidate(snippet="사내 행사 장소와 식사 메뉴를 검토했습니다")]).execute(
            _command()
        )
    )

    assert result is None


def test_builds_decision_feedback_with_delivery_scope() -> None:
    participant_a = uuid4()
    participant_b = uuid4()
    command = _command(
        participant_user_ids=[participant_b, participant_a, participant_b]
    )

    result = asyncio.run(
        _workflow(
            [_candidate(snippet="결제 승인 정책은 관리자 검토 후 적용하기로 확정했습니다")]
        ).execute(command)
    )

    assert result is not None
    assert result.meeting_id == command.meeting_id
    assert result.session_id == command.session_id
    assert result.feedback_type == "DECISION_REMINDER"
    assert result.audience_user_ids == sorted([participant_a, participant_b], key=str)
    assert result.from_sequence == 10
    assert result.to_sequence == 11
    assert len(result.sources) == 1


def test_builds_duplicate_feedback_only_with_meaningful_shared_terms() -> None:
    result = asyncio.run(
        _workflow(
            [_candidate(snippet="결제 승인 정책과 자동 승인 기준을 검토했습니다")]
        ).execute(_command())
    )

    assert result is not None
    assert result.feedback_type == "DUPLICATE_DISCUSSION"


def test_demo_gate_allows_semantically_retrieved_candidate_without_keyword_overlap() -> None:
    result = asyncio.run(
        _workflow(
            [_candidate(snippet="사내 행사 장소와 식사 메뉴를 검토했습니다", score=0.5)],
            score_threshold=0.45,
            allow_semantic_fallback=True,
        ).execute(_command())
    )

    assert result is not None
    assert result.feedback_type == "DUPLICATE_DISCUSSION"


def test_limits_long_source_excerpt_to_result_schema() -> None:
    result = asyncio.run(
        _workflow([_candidate(snippet=f"결제 승인 확정 {('상세 내용 ' * 300)}")]).execute(
            _command()
        )
    )

    assert result is not None
    assert len(result.message) <= 500
