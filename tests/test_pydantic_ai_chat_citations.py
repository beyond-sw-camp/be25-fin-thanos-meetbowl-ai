"""답변에 실제로 인용한 자료만 출처로 회수하는지 검증."""

from uuid import uuid4

from app.providers.pydantic_ai_chat import _select_cited_sources
from app.schemas.chat import ChatSource


def _source(title: str) -> ChatSource:
    return ChatSource(
        type="PERSONAL_MEMO",
        resource_id=uuid4(),
        title=title,
        snippet=f"{title} 본문",
        score=1.0,
    )


def test_only_cited_indices_are_returned_in_order() -> None:
    accumulated = [_source("A"), _source("B"), _source("C")]

    selected = _select_cited_sources(accumulated, [3, 1])

    assert [s.title for s in selected] == ["C", "A"]


def test_empty_citations_returns_no_sources() -> None:
    accumulated = [_source("A"), _source("B")]

    assert _select_cited_sources(accumulated, []) == []


def test_out_of_range_and_duplicate_indices_are_ignored() -> None:
    accumulated = [_source("A"), _source("B")]

    selected = _select_cited_sources(accumulated, [2, 2, 5, 0, -1])

    assert [s.title for s in selected] == ["B"]
