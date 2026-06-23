"""벡터 점수 리랭커의 문서 다양성 보장 검증."""

import asyncio
from uuid import UUID, uuid4

from app.providers.vector_score_reranker import VectorScoreReranker
from app.schemas.chat import ChatSource


def _source(resource_id: UUID, title: str, score: float) -> ChatSource:
    return ChatSource(
        type="PERSONAL_DRIVE_FILE",
        resource_id=resource_id,
        title=title,
        snippet=f"{title} 청크",
        score=score,
    )


def test_keeps_only_best_chunk_per_document() -> None:
    first = uuid4()
    second = uuid4()
    sources = [
        _source(first, "신뢰도 기법", 0.9),
        _source(first, "신뢰도 기법", 0.8),
        _source(second, "관련 도구", 0.7),
    ]

    kept = asyncio.run(
        VectorScoreReranker().rerank(
            query="LLM 신뢰도 자료", sources=sources, top_n=10
        )
    )

    assert [source.resource_id for source in kept] == [first, second]
    assert kept[0].score == 0.9


def test_document_diversity_still_respects_threshold_and_top_n() -> None:
    sources = [
        _source(uuid4(), "A", 0.9),
        _source(uuid4(), "B", 0.8),
        _source(uuid4(), "C", 0.4),
    ]

    kept = asyncio.run(
        VectorScoreReranker(score_threshold=0.5).rerank(
            query="q", sources=sources, top_n=1
        )
    )

    assert [source.title for source in kept] == ["A"]
