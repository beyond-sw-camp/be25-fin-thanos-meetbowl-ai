from app.core.cache import AsyncResultCache
from app.ports.embedding_provider import EmbeddingProvider


class CachingEmbeddingProvider:
    """질의 임베딩 결과를 텍스트 기준으로 캐시해 같은 검색의 반복 임베딩 호출을 없앤다.

    질의 임베딩은 텍스트만의 함수라 사용자 데이터가 섞이지 않으므로 요청 간 캐시도 안전하다.
    """

    def __init__(
        self, inner: EmbeddingProvider, cache: AsyncResultCache[list[float]]
    ) -> None:
        self._inner = inner
        self._cache = cache

    async def embed(self, text: str) -> list[float]:
        return await self._cache.get_or_compute(text, lambda: self._inner.embed(text))
