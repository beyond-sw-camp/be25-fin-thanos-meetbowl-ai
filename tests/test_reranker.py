"""FakeReranker가 질의 관련도로 재정렬하고 상위 N개로 자르는지 검증한다."""

import asyncio
from uuid import uuid4

from app.providers.fake_reranker import FakeReranker
from app.schemas.chat import ChatSource


def _source(title: str, snippet: str) -> ChatSource:
    return ChatSource(
        type="MINUTES", resource_id=uuid4(), title=title, snippet=snippet, score=0.5
    )


def test_fake_reranker_orders_by_query_token_overlap() -> None:
    low = _source("주간 안내", "점심 메뉴 공지입니다")
    high = _source("배포 회의록", "금요일 배포 일정 확정")

    result = asyncio.run(
        FakeReranker().rerank(query="배포 일정", sources=[low, high], top_n=10)
    )

    # 질의 토큰과 더 많이 겹치는 후보가 앞으로 온다.
    assert result[0] is high
    assert result[1] is low


def test_fake_reranker_truncates_to_top_n() -> None:
    sources = [_source(f"문서 {index}", "배포 일정") for index in range(5)]

    result = asyncio.run(
        FakeReranker().rerank(query="배포 일정", sources=sources, top_n=2)
    )

    assert len(result) == 2
