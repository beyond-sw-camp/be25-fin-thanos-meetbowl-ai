"""답변에 실제로 인용한 자료만 출처로 회수하는지 검증."""

from uuid import uuid4

from app.providers.pydantic_ai_chat import _normalize_answer_format, _select_cited_sources
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


def test_html_lists_are_converted_to_readable_plain_text() -> None:
    answer = _normalize_answer_format(
        "결론<ul><li>첫 번째</li><li><b>두 번째</b></li></ul><br>끝"
    )

    assert "<ul>" not in answer
    assert "- 첫 번째" in answer
    assert "- 두 번째" in answer
    assert "\n" in answer


def test_long_single_paragraph_is_split_every_three_sentences() -> None:
    answer = _normalize_answer_format("하나. 둘. 셋. 넷. 다섯. 여섯.")

    paragraphs = answer.split("\n\n")
    assert paragraphs == ["하나. 둘. 셋.", "넷. 다섯. 여섯."]
