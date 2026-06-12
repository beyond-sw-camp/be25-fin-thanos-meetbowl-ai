from typing import Any

from google import genai
from google.genai import types
from pydantic import Field

from app.core.errors import ProviderUnavailableError
from app.schemas.base import ApiModel
from app.schemas.chat import ChatSource

# reranker 프롬프트에 넣는 후보 본문 길이 상한(토큰 절약용).
_SNIPPET_PREVIEW_CHARS = 400


class _RankedItem(ApiModel):
    index: int = Field(ge=0)
    score: float


class _RankingResult(ApiModel):
    items: list[_RankedItem]


class GeminiReranker:
    """Gemini로 후보를 질의 관련도 0~1로 재채점해 정렬하는 운영용 reranker.

    한 번의 호출로 모든 후보를 채점한다. 호출/파싱 실패 시에는 원래 융합 순서를
    그대로 사용해 검색이 깨지지 않도록 graceful fallback 한다.
    """

    def __init__(
        self, *, api_key: str | None, model_name: str, client: Any | None = None
    ) -> None:
        self._api_key = api_key
        self._model_name = model_name
        self._client = client

    async def rerank(
        self, *, query: str, sources: list[ChatSource], top_n: int
    ) -> list[ChatSource]:
        """Gemini 관련도 점수로 재정렬해 상위 top_n개를 반환한다(실패 시 원순서 유지)."""
        if len(sources) <= 1:
            return sources[:top_n]
        try:
            result = await self._score(query, sources)
            ordered = self._apply_ranking(result, sources)
            return ordered[:top_n]
        except Exception:
            # 운영 중 reranker 오류가 검색 자체를 막지 않도록 융합 순서로 되돌린다.
            return sources[:top_n]

    async def _score(self, query: str, sources: list[ChatSource]) -> _RankingResult:
        prompt = self._build_prompt(query, sources)
        response = await self._get_client().aio.models.generate_content(
            model=self._model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.0,
                response_mime_type="application/json",
                response_json_schema=_RankingResult.model_json_schema(by_alias=True),
            ),
        )
        if not response.text:
            raise ProviderUnavailableError("Gemini reranker가 빈 응답을 반환했습니다.")
        return _RankingResult.model_validate_json(response.text)

    def _build_prompt(self, query: str, sources: list[ChatSource]) -> str:
        candidates = "\n\n".join(
            f"[{index}] {source.title}\n{source.snippet[:_SNIPPET_PREVIEW_CHARS]}"
            for index, source in enumerate(sources)
        )
        return (
            "다음 질문과 각 문서의 관련도를 0~1 사이 점수로 평가하세요.\n"
            "모든 문서를 index와 score로 빠짐없이 채점해 JSON으로만 답하세요.\n\n"
            f"질문: {query}\n\n"
            f"문서:\n{candidates}"
        )

    def _apply_ranking(
        self, result: _RankingResult, sources: list[ChatSource]
    ) -> list[ChatSource]:
        ordered: list[ChatSource] = []
        seen: set[int] = set()
        for item in sorted(result.items, key=lambda candidate: candidate.score, reverse=True):
            if 0 <= item.index < len(sources) and item.index not in seen:
                ordered.append(sources[item.index])
                seen.add(item.index)
        # 모델이 누락한 후보는 원래(융합) 순서대로 뒤에 붙인다.
        for index, source in enumerate(sources):
            if index not in seen:
                ordered.append(source)
        return ordered

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        if not self._api_key:
            raise ProviderUnavailableError("GEMINI_API_KEY가 설정되지 않았습니다.")
        self._client = genai.Client(api_key=self._api_key)
        return self._client
