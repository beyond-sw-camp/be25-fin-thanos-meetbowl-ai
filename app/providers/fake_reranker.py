import re

from app.schemas.chat import ChatSource

_TOKEN_PATTERN = re.compile(r"[0-9A-Za-z가-힣]+")


class FakeReranker:
    """질의와 (제목+본문) 토큰 겹침으로 재정렬하는 결정적 reranker(테스트/fake용).

    실제 cross-encoder/LLM reranker 없이 RAG 재정렬 흐름을 검증하기 위한 대체 구현이다.
    """

    async def rerank(
        self, *, query: str, sources: list[ChatSource], top_n: int
    ) -> list[ChatSource]:
        """질의 토큰과 겹치는 정도가 큰 순으로 정렬해 상위 top_n개를 반환한다."""
        query_tokens = set(_TOKEN_PATTERN.findall(query.lower()))

        def overlap(source: ChatSource) -> int:
            text = f"{source.title} {source.snippet}".lower()
            return len(query_tokens & set(_TOKEN_PATTERN.findall(text)))

        # sorted는 안정 정렬이라 동점은 원래 순서(=융합 점수 순)를 유지한다.
        ranked = sorted(sources, key=overlap, reverse=True)
        return ranked[:top_n]
