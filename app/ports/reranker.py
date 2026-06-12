from typing import Protocol

from app.schemas.chat import ChatSource


class Reranker(Protocol):
    """검색 후보를 질의 관련도로 재채점·재정렬해 상위 N개를 고르는 reranker 계약."""

    async def rerank(
        self, *, query: str, sources: list[ChatSource], top_n: int
    ) -> list[ChatSource]:
        """query 기준으로 sources를 재정렬해 상위 top_n개를 반환한다."""
        ...
