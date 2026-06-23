"""복합 질문의 병렬 검색 결과가 질의별로 고르게 합쳐지는지 검증."""

import asyncio
from uuid import uuid4

from app.rag.multi_query_search import search_queries_in_parallel
from app.schemas.chat import ChatCommand, ChatSource


class _EmbeddingProvider:
    async def embed(self, text: str) -> list[float]:
        return [float(len(text))]


class _Retriever:
    def __init__(self, results: dict[str, list[ChatSource]]) -> None:
        self._results = results

    async def search(self, *, query: str, **_kwargs) -> list[ChatSource]:
        await asyncio.sleep(0)
        return self._results[query]


class _Reranker:
    async def rerank(
        self, *, query: str, sources: list[ChatSource], top_n: int
    ) -> list[ChatSource]:
        return sources[:top_n]


def _source(resource_id, title: str, score: float) -> ChatSource:
    return ChatSource(
        type="PERSONAL_DRIVE_FILE",
        resource_id=resource_id,
        title=title,
        snippet=title,
        score=score,
    )


def _command() -> ChatCommand:
    return ChatCommand(
        request_id=uuid4(),
        correlation_id=uuid4(),
        user_id=uuid4(),
        question="q",
    )


def test_round_robin_preserves_query_coverage_and_deduplicates_documents() -> None:
    shared = uuid4()
    results = {
        "methods": [
            _source(shared, "신뢰도 기법", 0.9),
            _source(uuid4(), "프롬프트", 0.8),
        ],
        "resources": [
            _source(shared, "신뢰도 기법", 0.85),
            _source(uuid4(), "관련 도구", 0.7),
        ],
    }

    merged = asyncio.run(
        search_queries_in_parallel(
            queries=["methods", "resources"],
            command=_command(),
            embedding_provider=_EmbeddingProvider(),
            retriever=_Retriever(results),
            reranker=_Reranker(),
            source_types=None,
            candidate_pool=10,
            top_n=3,
        )
    )

    assert [source.title for source in merged] == [
        "신뢰도 기법",
        "프롬프트",
        "관련 도구",
    ]
