import re

from app.schemas.chat import ChatSource

_TOKEN_PATTERN = re.compile(r"[0-9A-Za-z가-힣]+")


class FakeReranker:
    """질의와 (제목+본문) 토큰 겹침으로 재정렬하는 결정적 reranker(테스트/fake용).

    실제 cross-encoder/LLM reranker 없이 RAG 재정렬·무근거 차단 흐름을 검증하기 위한 대체 구현이다.
    """

    def __init__(self, score_threshold: float = 0.0) -> None:
        # 관련도가 이 값 미만인 후보는 버린다. 0.0이면 무근거 차단 비활성(전부 통과).
        self._score_threshold = score_threshold

    async def rerank(
        self, *, query: str, sources: list[ChatSource], top_n: int
    ) -> list[ChatSource]:
        """질의 토큰 겹침 비율(0~1)을 score로 매겨 정렬하고, 임계값 미만은 버린 뒤 상위 top_n개를 반환한다."""
        query_tokens = set(_TOKEN_PATTERN.findall(query.lower()))

        def overlap_ratio(source: ChatSource) -> float:
            if not query_tokens:
                return 0.0
            text_tokens = set(_TOKEN_PATTERN.findall(f"{source.title} {source.snippet}".lower()))
            return len(query_tokens & text_tokens) / len(query_tokens)

        rescored = [
            source.model_copy(update={"score": overlap_ratio(source)})
            for source in sources
        ]
        rescored.sort(key=lambda source: source.score, reverse=True)
        kept = [source for source in rescored if source.score >= self._score_threshold]
        return kept[:top_n]
