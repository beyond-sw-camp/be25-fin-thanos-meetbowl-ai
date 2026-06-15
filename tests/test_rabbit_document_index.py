"""BE가 발행한 색인 이벤트를 AI가 소비해 Qdrant에 색인하는 통합 테스트.

BE의 `document.index.requested` 이벤트(EventEnvelope) → 소비자 → translator →
색인 workflow → Qdrant upsert 까지 한 흐름으로 검증한다(Qdrant는 HTTP mock).
"""

import asyncio
import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

import httpx

from app.events.idempotency import InMemoryEventTracker
from app.events.rabbit import DocumentIndexEventProcessor
from app.providers.fake_embedding import FakeEmbeddingProvider
from app.rag.qdrant_index import QdrantDocumentIndexer
from app.schemas.events import EventEnvelope
from app.workflows.document_indexing import DocumentIndexingWorkflow


class FakeMessage:
    def __init__(self, body: bytes) -> None:
        self.body = body
        self.acked = 0
        self.requeues: list[bool] = []

    async def ack(self) -> None:
        self.acked += 1

    async def reject(self, *, requeue: bool) -> None:
        self.requeues.append(requeue)


def index_requested_event(
    *,
    document_id: UUID,
    owner_user_id: UUID,
    event_id: UUID | None = None,
) -> EventEnvelope:
    """BE의 RabbitEventPublisher가 발행하는 것과 동일한 형식의 색인 이벤트."""
    return EventEnvelope(
        event_id=event_id or uuid4(),
        event_type="document.index.requested",
        occurred_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        producer="api-server",
        version=1,
        correlation_id=uuid4(),
        payload={
            "documentId": str(document_id),
            "documentType": "MEETING_MINUTES",
            "organizationId": str(uuid4()),
            "ownerUserId": str(owner_user_id),
            "title": "배포 회의록",
            "content": "금요일 배포로 결정했습니다.",
            "accessScope": {
                "userIds": [str(owner_user_id)],
                "departmentIds": [],
                "sharedWorkspaceIds": [],
            },
        },
    )


def _qdrant_handler(requests: list[httpx.Request]):
    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "GET":
            return httpx.Response(404)  # collection 없음 → 생성 경로
        return httpx.Response(200, json={"status": "ok"})

    return handler


def _processor(client: httpx.AsyncClient, tracker: InMemoryEventTracker) -> DocumentIndexEventProcessor:
    workflow = DocumentIndexingWorkflow(
        embedding_provider=FakeEmbeddingProvider(),
        indexer=QdrantDocumentIndexer(
            qdrant_url="http://qdrant",
            qdrant_collection="documents",
            http_client=client,
        ),
    )
    return DocumentIndexEventProcessor(
        workflow=workflow, tracker=tracker, max_retries=3
    )


def test_be_index_event_is_consumed_and_indexed_into_qdrant() -> None:
    requests: list[httpx.Request] = []
    document_id = uuid4()
    owner_user_id = uuid4()
    event = index_requested_event(document_id=document_id, owner_user_id=owner_user_id)

    async def run() -> FakeMessage:
        async with httpx.AsyncClient(transport=httpx.MockTransport(_qdrant_handler(requests))) as client:
            message = FakeMessage(event.model_dump_json(by_alias=True).encode())
            await _processor(client, InMemoryEventTracker()).process(message)
            return message

    message = asyncio.run(run())

    # 이벤트가 정상 처리되어 ack 되었다.
    assert message.acked == 1
    assert message.requeues == []
    # Qdrant upsert 본문에 문서·소유자·유형 metadata가 저장됐다(MEETING_MINUTES→MINUTES).
    upsert_body = requests[-1].read().decode()
    assert str(document_id) in upsert_body
    assert str(owner_user_id) in upsert_body
    assert "MINUTES" in upsert_body


def test_duplicate_index_event_is_acked_without_reindexing() -> None:
    requests: list[httpx.Request] = []
    event = index_requested_event(document_id=uuid4(), owner_user_id=uuid4())
    tracker = InMemoryEventTracker()

    async def run() -> tuple[FakeMessage, int]:
        async with httpx.AsyncClient(transport=httpx.MockTransport(_qdrant_handler(requests))) as client:
            processor = _processor(client, tracker)
            await processor.process(FakeMessage(event.model_dump_json(by_alias=True).encode()))
            after_first = len(requests)
            duplicate = FakeMessage(event.model_dump_json(by_alias=True).encode())
            await processor.process(duplicate)
            return duplicate, after_first

    duplicate, after_first = asyncio.run(run())

    # 중복 이벤트는 재색인 없이 ack 되고, Qdrant 호출이 늘지 않는다.
    assert duplicate.acked == 1
    assert len(requests) == after_first


def test_invalid_message_is_rejected_to_dlq() -> None:
    async def run() -> FakeMessage:
        async with httpx.AsyncClient(transport=httpx.MockTransport(_qdrant_handler([]))) as client:
            message = FakeMessage(b"not-json")
            await _processor(client, InMemoryEventTracker()).process(message)
            return message

    message = asyncio.run(run())

    assert message.acked == 0
    assert message.requeues == [False]


def test_unsupported_event_type_is_rejected_to_dlq() -> None:
    event = index_requested_event(
        document_id=uuid4(), owner_user_id=uuid4()
    ).model_copy(update={"event_type": "document.unknown"})

    async def run() -> FakeMessage:
        async with httpx.AsyncClient(transport=httpx.MockTransport(_qdrant_handler([]))) as client:
            message = FakeMessage(event.model_dump_json(by_alias=True).encode())
            await _processor(client, InMemoryEventTracker()).process(message)
            return message

    message = asyncio.run(run())

    assert message.requeues == [False]


def test_indexing_failure_requeues_until_max_then_rejects() -> None:
    class FailingWorkflow:
        async def execute(self, _: Any) -> Any:
            raise RuntimeError("Qdrant down")

    processor = DocumentIndexEventProcessor(
        workflow=FailingWorkflow(),
        tracker=InMemoryEventTracker(),
        max_retries=3,
    )
    event = index_requested_event(document_id=uuid4(), owner_user_id=uuid4())
    requeues: list[bool] = []

    for _ in range(4):
        message = FakeMessage(event.model_dump_json(by_alias=True).encode())
        asyncio.run(processor.process(message))
        requeues.extend(message.requeues)

    # 일시 실패는 3번 재시도 후 DLQ로 보낸다.
    assert requeues == [True, True, True, False]
