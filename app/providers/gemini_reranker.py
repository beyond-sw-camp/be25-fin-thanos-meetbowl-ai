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
        self,
        *,
        api_key: str | None,
        model_name: str,
        client: Any | None = None,
        score_threshold: float = 0.0,
    ) -> None:
        self._api_key = api_key
        self._model_name = model_name
        self._client = client
        # 관련도가 이 값 미만인 후보는 버린다. 0.0이면 무근거 차단 비활성(전부 통과).
        self._score_threshold = score_threshold

    async def rerank(
        self, *, query: str, sources: list[ChatSource], top_n: int
    ) -> list[ChatSource]:
        """Gemini 관련도(0~1)를 점수로 매겨 재정렬하고, 임계값 미만은 버린 뒤 상위 top_n개를 반환한다.

        채점이 실패하면 무근거 차단을 적용하지 않고 원래 순서를 유지한다(검색을 막지 않기 위해).
        """
        if len(sources) <= 1:
            return sources[:top_n]
        try:
            result = await self._score(query, sources)
        except Exception:
            # 운영 중 reranker 오류가 검색 자체를 막지 않도록 융합 순서로 되돌린다.
            return sources[:top_n]
        scored = self._apply_scores(result, sources)
        kept = [source for source in scored if source.score >= self._score_threshold]
        return kept[:top_n]

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

    def _apply_scores(
        self, result: _RankingResult, sources: list[ChatSource]
    ) -> list[ChatSource]:
        """각 후보에 Gemini 관련도(0~1)를 score로 부여하고 관련도 내림차순으로 정렬한다.

        모델이 채점하지 않은 후보는 관련도 0으로 둬, 임계값 차단에서 자연스럽게 걸러지게 한다.
        """
        score_by_index = {
            item.index: item.score
            for item in result.items
            if 0 <= item.index < len(sources)
        }
        rescored = [
            source.model_copy(
                update={"score": max(0.0, min(1.0, score_by_index.get(index, 0.0)))}
            )
            for index, source in enumerate(sources)
        ]
        rescored.sort(key=lambda source: source.score, reverse=True)
        return rescored

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        if not self._api_key:
            raise ProviderUnavailableError("GEMINI_API_KEY가 설정되지 않았습니다.")
        self._client = genai.Client(api_key=self._api_key)
        return self._client
