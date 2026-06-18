"""list_by_owner: 날짜 필터·문서 단위 중복 제거·최신순·limit 검증."""

import asyncio
import json
from uuid import uuid4

import httpx

from app.rag.qdrant_chat import QdrantChatRetriever
from app.schemas.chat import ChatCommand


def _command() -> ChatCommand:
    return ChatCommand(
        request_id=uuid4(),
        correlation_id=uuid4(),
        user_id=uuid4(),
        organization_id=None,
        question="x",
        message_history=[],
        shared_workspace_ids=[],
    )


def _point(document_id: str, title: str, created_at: str, chunk: int = 0) -> dict:
    return {
        "id": str(uuid4()),
        "payload": {
            "sourceType": "PERSONAL_MEMO",
            "documentId": document_id,
            "title": title,
            "snippet": f"{title} 본문",
            "createdAt": created_at,
            "chunkIndex": chunk,
        },
    }


def _retriever(points: list[dict], capture: dict | None = None) -> QdrantChatRetriever:
    def handler(request: httpx.Request) -> httpx.Response:
        if capture is not None:
            capture["path"] = request.url.path
            capture["body"] = json.loads(request.content)
        return httpx.Response(200, json={"result": {"points": points}})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return QdrantChatRetriever(
        qdrant_url="http://q", qdrant_collection="c", http_client=client
    )


def test_filters_by_created_after_and_sorts_newest_first() -> None:
    d1, d2, d3 = str(uuid4()), str(uuid4()), str(uuid4())
    points = [
        _point(d1, "어제 메모", "2026-06-16T10:00:00Z"),
        _point(d2, "오늘 아침 메모", "2026-06-17T01:00:00Z"),
        _point(d3, "오늘 오후 메모", "2026-06-17T08:00:00Z"),
    ]
    retriever = _retriever(points)

    docs = asyncio.run(
        retriever.list_by_owner(command=_command(), created_after="2026-06-17")
    )

    # 어제 메모 제외, 오늘 것만 최신순
    assert [d.title for d in docs] == ["오늘 오후 메모", "오늘 아침 메모"]


def test_created_after_date_is_interpreted_as_kst_midnight() -> None:
    # 2026-06-16T16:00Z == 2026-06-17 01:00 KST → KST 기준 '오늘'이므로 포함돼야 한다.
    # (UTC로 해석했다면 2026-06-17T00:00Z 경계에 걸려 제외됐을 항목)
    document_id = str(uuid4())
    points = [_point(document_id, "KST 자정 직후 메모", "2026-06-16T16:00:00Z")]
    retriever = _retriever(points)

    docs = asyncio.run(
        retriever.list_by_owner(command=_command(), created_after="2026-06-17")
    )

    assert [d.title for d in docs] == ["KST 자정 직후 메모"]


def test_created_before_includes_whole_end_day_kst() -> None:
    # created_before='2026-06-10' → 6월 10일(KST) 전체 포함, 6월 11일(KST)은 제외.
    inside, outside = str(uuid4()), str(uuid4())
    points = [
        _point(inside, "10일 자료", "2026-06-10T05:00:00Z"),   # 14:00 KST 6/10 → 포함
        _point(outside, "11일 자료", "2026-06-10T16:00:00Z"),  # 01:00 KST 6/11 → 제외
    ]
    retriever = _retriever(points)

    docs = asyncio.run(
        retriever.list_by_owner(command=_command(), created_before="2026-06-10")
    )

    assert [d.title for d in docs] == ["10일 자료"]


def test_count_by_owner_counts_distinct_documents_in_range() -> None:
    doc_a, doc_b, doc_c = str(uuid4()), str(uuid4()), str(uuid4())
    points = [
        _point(doc_a, "A", "2026-06-17T01:00:00Z", chunk=0),
        _point(doc_a, "A", "2026-06-17T01:00:00Z", chunk=1),  # 같은 문서 → 1건
        _point(doc_b, "B", "2026-06-17T02:00:00Z"),
        _point(doc_c, "C(어제)", "2026-06-15T02:00:00Z"),  # 범위 밖
    ]
    retriever = _retriever(points)

    count = asyncio.run(
        retriever.count_by_owner(command=_command(), created_after="2026-06-17")
    )

    assert count == 2


def test_dedupes_chunks_of_same_document() -> None:
    document_id = str(uuid4())
    points = [
        _point(document_id, "긴 메모", "2026-06-17T08:00:00Z", chunk=0),
        _point(document_id, "긴 메모", "2026-06-17T08:00:00Z", chunk=1),
    ]
    retriever = _retriever(points)

    docs = asyncio.run(retriever.list_by_owner(command=_command()))

    assert len(docs) == 1


def test_limit_caps_document_count() -> None:
    points = [
        _point(str(uuid4()), f"메모{i}", f"2026-06-17T0{i}:00:00Z") for i in range(5)
    ]
    retriever = _retriever(points)

    docs = asyncio.run(retriever.list_by_owner(command=_command(), limit=2))

    assert len(docs) == 2


def test_uses_scroll_endpoint_without_vector() -> None:
    capture: dict = {}
    retriever = _retriever([], capture)

    asyncio.run(retriever.list_by_owner(command=_command()))

    assert capture["path"].endswith("/points/scroll")
    assert capture["body"]["with_vector"] is False
    assert "filter" in capture["body"]
