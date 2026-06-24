"""질의 확장: 번역·인명 별칭 결정적 주입과 실패 시 fail-open 검증."""

import asyncio

from app.ports.generation import StructuredGenerationRequest, StructuredGenerationResult
from app.rag.query_expansion import QueryExpander, QueryExpansion


class _FakeGenerationPort:
    def __init__(self, expansion: QueryExpansion) -> None:
        self._expansion = expansion
        self.calls = 0

    async def generate_structured(
        self, request: StructuredGenerationRequest
    ) -> StructuredGenerationResult:
        self.calls += 1
        output = request.response_schema.model_validate(self._expansion.model_dump())
        return StructuredGenerationResult(output=output, model_name="fake-expander")


class _FailingGenerationPort:
    async def generate_structured(
        self, request: StructuredGenerationRequest
    ) -> StructuredGenerationResult:
        raise RuntimeError("expansion model unavailable")


def test_expand_includes_translation_and_llm_aliases() -> None:
    port = _FakeGenerationPort(
        QueryExpansion(
            translation="Who got an S rating in the H1 HR evaluation",
            name_aliases=["Some Person"],
            search_facets=["인사평가 신뢰도", "직원 업무 자료"],
        )
    )
    expander = QueryExpander(structured_generation_port=port, model_profile="x")

    result = asyncio.run(expander.expand("상반기 인사평가 S등급 직원"))

    assert "상반기 인사평가 S등급 직원" in result
    assert "Who got an S rating" in result
    assert "Some Person" in result
    assert "인사평가 신뢰도" in result
    assert "직원 업무 자료" in result


def test_expand_limits_search_facets_to_three() -> None:
    port = _FakeGenerationPort(QueryExpansion(search_facets=["A", "B", "C", "D"]))
    expander = QueryExpander(structured_generation_port=port, model_profile="x")

    result = asyncio.run(expander.expand("복합 질문"))

    assert "A" in result and "B" in result and "C" in result
    assert "D" not in result


def test_simple_question_keeps_one_search() -> None:
    port = _FakeGenerationPort(
        QueryExpansion(translation="What is RAG?", search_facets=[])
    )
    expander = QueryExpander(structured_generation_port=port, model_profile="x")

    queries = asyncio.run(expander.search_queries("RAG가 뭐야?"))

    assert len(queries) == 1
    assert "RAG가 뭐야?" in queries[0]
    assert "What is RAG?" in queries[0]


def test_compound_question_uses_at_most_three_searches() -> None:
    port = _FakeGenerationPort(
        QueryExpansion(
            translation="How to improve LLM reliability and recommended resources",
            search_facets=["신뢰도 개선 방법", "RAG 구현", "평가 도구"],
        )
    )
    expander = QueryExpander(structured_generation_port=port, model_profile="x")

    queries = asyncio.run(
        expander.search_queries("LLM 신뢰도를 올리는 방법과 자료를 추천해줘")
    )

    assert len(queries) == 3
    assert "신뢰도 개선 방법" in queries
    assert "RAG 구현" in queries


def test_glossary_injects_opposite_spelling_deterministically() -> None:
    port = _FakeGenerationPort(QueryExpansion(translation="", name_aliases=[]))
    expander = QueryExpander(structured_generation_port=port, model_profile="x")

    # 한국어 이름 → 영문 표기 주입
    assert "Dawit Lee" in asyncio.run(expander.expand("이다윗이 맡은 업무"))
    # 영문 이름 → 한국어 표기 주입(대소문자 무관)
    assert "최진우" in asyncio.run(expander.expand("what is jinwoo choi working on"))


def test_expand_fails_open_to_original_query_with_glossary() -> None:
    expander = QueryExpander(
        structured_generation_port=_FailingGenerationPort(), model_profile="x"
    )

    result = asyncio.run(expander.expand("이다윗 업무"))

    # 확장 호출이 실패해도 검색을 막지 않고 원문 + 사전 별칭은 유지한다.
    assert "이다윗 업무" in result
    assert "Dawit Lee" in result


def test_no_duplicate_aliases() -> None:
    # 사전과 LLM이 같은 별칭을 내도 한 번만 포함되어야 한다(번역문엔 별칭을 넣지 않는다).
    port = _FakeGenerationPort(
        QueryExpansion(translation="", name_aliases=["Dawit Lee"])
    )
    expander = QueryExpander(structured_generation_port=port, model_profile="x")

    result = asyncio.run(expander.expand("이다윗 업무"))

    assert result.count("Dawit Lee") == 1
