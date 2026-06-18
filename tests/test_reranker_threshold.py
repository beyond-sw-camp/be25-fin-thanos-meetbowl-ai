"""무근거 차단: 리랭크 관련도 임계값 미만 후보가 걸러지는지 검증(FakeReranker 결정적)."""

import asyncio
from uuid import uuid4

from app.providers.fake_reranker import FakeReranker
from app.schemas.chat import ChatSource


def _source(title: str, snippet: str) -> ChatSource:
    return ChatSource(
        type="PERSONAL_MEMO",
        resource_id=uuid4(),
        title=title,
        snippet=snippet,
        score=0.01,
    )


def test_below_threshold_sources_are_dropped() -> None:
    sources = [
        _source("OKR 회의 메모", "신규 가입자 목표와 전환율 개선"),  # 질의와 겹침 큼
        _source("점심 메뉴", "오늘 점심은 김치찌개"),  # 무관
    ]
    reranker = FakeReranker(score_threshold=0.5)

    kept = asyncio.run(
        reranker.rerank(query="OKR 가입자 목표", sources=sources, top_n=10)
    )

    titles = [s.title for s in kept]
    assert "OKR 회의 메모" in titles
    assert "점심 메뉴" not in titles


def test_all_dropped_when_nothing_relevant() -> None:
    sources = [_source("점심 메뉴", "김치찌개"), _source("주차 안내", "지하 2층")]
    reranker = FakeReranker(score_threshold=0.5)

    kept = asyncio.run(
        reranker.rerank(query="OKR 목표 알려줘", sources=sources, top_n=10)
    )

    # 관련 자료가 없으면 전부 걸러져 빈 목록 → 검색 도구가 '근거 없음'을 반환하게 된다.
    assert kept == []


def test_threshold_zero_keeps_all_and_sets_scores() -> None:
    sources = [_source("A", "OKR 목표"), _source("B", "무관 내용")]
    reranker = FakeReranker(score_threshold=0.0)

    kept = asyncio.run(reranker.rerank(query="OKR 목표", sources=sources, top_n=10))

    assert len(kept) == 2
    # 관련도가 score로 매겨지고(0~1), 관련 높은 자료가 앞에 온다.
    assert kept[0].title == "A"
    assert 0.0 <= kept[0].score <= 1.0
