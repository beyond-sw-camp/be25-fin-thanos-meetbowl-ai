"""같은 문서의 여러 근거 청크 병합 검증."""

from uuid import uuid4

import pytest

from app.rag.source_merge import merge_chat_sources
from app.schemas.chat import ChatSource


def _source(resource_id, snippet: str, score: float) -> ChatSource:
    return ChatSource(
        type="PERSONAL_DRIVE_FILE",
        resource_id=resource_id,
        title="guide.pdf",
        snippet=snippet,
        score=score,
    )


def test_merges_distinct_chunks_and_keeps_best_score() -> None:
    resource_id = uuid4()

    merged = merge_chat_sources(
        _source(resource_id, "Harmony 메시지 역할", 0.8),
        _source(resource_id, "정책은 Instruction과 Criteria로 구성", 0.6),
    )

    assert "Harmony 메시지 역할" in merged.snippet
    assert "Instruction과 Criteria" in merged.snippet
    assert merged.score == 0.8


def test_rejects_different_documents() -> None:
    with pytest.raises(ValueError):
        merge_chat_sources(
            _source(uuid4(), "A", 0.8),
            _source(uuid4(), "B", 0.7),
        )


def test_long_chunks_share_context_budget_instead_of_dropping_later_evidence() -> None:
    resource_id = uuid4()

    merged = merge_chat_sources(
        _source(resource_id, "FIRST " + "a" * 1_900, 0.9),
        _source(resource_id, "POLICY Instruction Definitions Criteria Examples", 0.8),
    )

    assert len(merged.snippet) <= 2_000
    assert "FIRST" in merged.snippet
    assert "POLICY Instruction Definitions Criteria Examples" in merged.snippet
