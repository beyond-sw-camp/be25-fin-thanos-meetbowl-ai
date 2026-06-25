"""답변에 실제로 인용한 자료만 출처로 회수하는지 검증."""

from uuid import uuid4

from app.providers.pydantic_ai_chat import (
    _accumulate_sources,
    _format_with_citation_numbers,
    _normalize_answer_format,
    _select_answer_sources,
    _select_cited_sources,
)
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


def test_answer_sources_do_not_fall_back_when_model_omits_citations() -> None:
    accumulated = [_source("A"), _source("B"), _source("C"), _source("D")]

    selected = _select_answer_sources(
        accumulated,
        [],
        "결론: A와 B 문서에서 확인되는 일정은 서로 다릅니다.",
    )

    assert selected == []


def test_answer_sources_do_not_fall_back_for_no_evidence_answer() -> None:
    accumulated = [_source("A"), _source("B")]

    selected = _select_answer_sources(
        accumulated,
        [],
        "현재 제공된 업무 자료에서는 관련 내용을 찾을 수 없습니다.",
    )

    assert selected == []


def test_html_lists_are_converted_to_readable_plain_text() -> None:
    answer = _normalize_answer_format(
        "결론<ul><li>첫 번째</li><li><b>두 번째</b></li></ul><br>끝"
    )

    assert "<ul>" not in answer
    assert "- 첫 번째" in answer
    assert "- 두 번째" in answer
    assert "\n" in answer


def test_model_generated_source_footer_is_removed_from_answer() -> None:
    answer = _normalize_answer_format(
        "결론: CSU 사례는 460,000명 이상의 학생을 대상으로 합니다.\n\n"
        "참고한 자료: OpenAI and the CSU system bring AI.pdf"
    )

    assert "참고한 자료" not in answer
    assert "OpenAI and the CSU system bring AI.pdf" not in answer
    assert "460,000명" in answer


def test_formatted_sources_separate_metadata_from_body() -> None:
    source = _source("Introducing data residency in Europe _ OpenAI.pdf")
    accumulated = []
    _accumulate_sources(accumulated, [source])

    formatted = _format_with_citation_numbers(accumulated, [source])

    assert "[1] Introducing data residency in Europe _ OpenAI.pdf" in formatted
    assert "자료 유형: PERSONAL_MEMO" in formatted
    assert "본문:\nIntroducing data residency in Europe _ OpenAI.pdf 본문" in formatted


def test_long_single_paragraph_is_split_every_three_sentences() -> None:
    answer = _normalize_answer_format("하나. 둘. 셋. 넷. 다섯. 여섯.")

    paragraphs = answer.split("\n\n")
    assert paragraphs == ["하나. 둘. 셋.", "넷. 다섯. 여섯."]
