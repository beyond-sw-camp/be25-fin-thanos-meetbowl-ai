import logging

from pydantic import BaseModel, Field

from app.core.cache import AsyncResultCache
from app.ports.generation import (
    StructuredGenerationPort,
    StructuredGenerationRequest,
)

logger = logging.getLogger("uvicorn.error")

# 원문·번역·요구별 검색을 모두 보존하되, 단일 질문이 과도한 검색을 일으키지 않게 한다.
_MAX_SEARCH_QUERIES = 4
_MAX_PARALLEL_SEARCHES = 3

# 양국어 표기가 흔들리면 멀티홉 검색이 끊기는 핵심 인물/고유명사. 질의에 한쪽 표기가 보이면
# 반대 표기를 결정적으로 주입해 LLM 음역의 비결정성에 의존하지 않게 한다.
_DEFAULT_NAME_GLOSSARY: dict[str, str] = {
    "이다윗": "Dawit Lee",
    "최진우": "Jinwoo Choi",
    "박서연": "Suhyun Park",
    "김민지": "Minji Kim",
}

_EXPANSION_PROMPT = """다음 검색 질의를 교차언어 검색에 쓸 수 있게 확장하라.
- translation: 질의를 반대 언어로 번역하라(한국어 질의면 영어로, 영어 질의면 한국어로). 의미를 보존하고 핵심 키워드를 살려라.
- name_aliases: 질의에 인명·조직명 등 고유명사가 있으면 다른 언어/음역 표기를 넣어라(예: 한국어 이름이면 영문 음역). 없으면 빈 배열.
- search_facets: 질문이 설명·구현 방법·자료 추천처럼 여러 요구를 함께 포함하면, 각 요구의 근거를 찾기 위한 구체적인 독립 검색어를 최대 3개 만들어라. 질문의 제품명·문서명·기술 용어를 각 검색어에 보존하고, '방법', '문서 구조 추천' 같은 일반적 표현만 남기지 마라. 단순 질문이면 빈 배열. 존재하지 않는 문서명은 만들지 마라.
예시: 'gpt-oss를 Harmony와 safeguard 문서 기준으로 안전성 분류에 적용할 구조'라면 'Harmony system developer user assistant role channel message format', 'gpt-oss-safeguard policy prompt Instruction Definitions Criteria Examples output schema', 'gpt-oss-safeguard production integration pre-filter post-filter classifier'처럼 나눠라.

질의: {query}"""


class QueryExpansion(BaseModel):
    translation: str = Field(
        default="",
        description="질의를 반대 언어로 번역한 문장(한국어면 영어, 영어면 한국어)",
    )
    name_aliases: list[str] = Field(
        default_factory=list,
        description="질의에 등장하는 고유명사의 다른 언어/음역 표기 목록",
    )
    search_facets: list[str] = Field(
        default_factory=list,
        description="복합 질문의 요구별 독립 검색어(최대 3개)",
    )


class QueryExpander:
    """검색 직전 질의를 원문 + 번역 + 인명 별칭으로 확장해 교차언어 검색을 결정적으로 만든다.

    dense는 확장 질의 임베딩으로, sparse는 확장 질의 토큰으로 영어/한국어 문서 모두에 매칭된다.
    표시·인용용 데이터는 건드리지 않고 검색 입력에만 적용한다.
    """

    def __init__(
        self,
        *,
        structured_generation_port: StructuredGenerationPort,
        model_profile: str,
        glossary: dict[str, str] | None = None,
        cache: AsyncResultCache[list[str]] | None = None,
    ) -> None:
        self._port = structured_generation_port
        self._model_profile = model_profile
        self._glossary = _DEFAULT_NAME_GLOSSARY if glossary is None else glossary
        self._cache = cache

    async def expand(self, query: str) -> str:
        """하위 호환용으로 확장 질의를 하나의 문자열로 반환한다."""
        return "\n".join(await self.expand_queries(query))

    async def search_queries(self, query: str) -> list[str]:
        """단순 질문은 혼합 검색 1회, 복합 질문은 요구별 최대 3회 검색으로 계획한다.

        원문+번역만 있는 경우는 기존처럼 하나의 검색어로 합쳐 속도를 유지한다.
        search_facets이 있을 때만 기본 질의와 각 facet을 별도 검색한다.
        """
        expanded = await self.expand_queries(query)
        if len(expanded) <= 2:
            return ["\n".join(expanded)]
        # 첫 두 항목은 원문(+별칭)과 번역이므로 하나의 기본 검색으로 합친다.
        base_query = "\n".join(expanded[:2])
        return [base_query, *expanded[2:]][:_MAX_PARALLEL_SEARCHES]

    async def expand_queries(self, query: str) -> list[str]:
        """원문·번역·요구별 질의를 별도 검색어로 반환한다.

        확장은 질의만의 함수이고 비싼 LLM 호출을 포함하므로, 캐시가 있으면 같은 질의 재사용한다.
실패하면 원문(+사전 별칭)으로 fail-open한다.
        """
        if self._cache is not None:
            return await self._cache.get_or_compute(
                query, lambda: self._compute_queries(query)
            )
        return await self._compute_queries(query)

    async def _compute_queries(self, query: str) -> list[str]:
        # 사전 별칭은 LLM 성공 여부와 무관하게 항상 결정적으로 포함한다.
        aliases = self._glossary_aliases(query)
        translation = ""
        facets: list[str] = []
        try:
            result = await self._port.generate_structured(
                StructuredGenerationRequest(
                    prompt=_EXPANSION_PROMPT.format(query=query),
                    response_schema=QueryExpansion,
                    model_profile=self._model_profile,
                    temperature=0.0,
                )
            )
            expansion = result.output
            if expansion.translation.strip():
                translation = expansion.translation.strip()
            facets = [
                facet.strip() for facet in expansion.search_facets[:3] if facet.strip()
            ]
            aliases.extend(a.strip() for a in expansion.name_aliases if a.strip())
        except Exception as exc:
            # 검색을 절대 막지 않는다. 확장 실패는 원문 검색으로 강등할 뿐이다.
            logger.warning("query expansion failed, falling back to original query: %s", exc)

        deduped_aliases = list(dict.fromkeys(aliases))
        original = query
        if deduped_aliases:
            original = f"{query}\n{' '.join(deduped_aliases)}"
        queries = [original]
        if translation:
            queries.append(translation)
        queries.extend(facets)
        return list(dict.fromkeys(queries))[:_MAX_SEARCH_QUERIES]

    def _glossary_aliases(self, query: str) -> list[str]:
        """질의에 사전의 한쪽 표기가 등장하면 반대 표기를 별칭으로 반환한다."""
        lowered = query.lower()
        aliases: list[str] = []
        for korean, english in self._glossary.items():
            if korean in query:
                aliases.append(english)
            elif english.lower() in lowered:
                aliases.append(korean)
        return aliases
