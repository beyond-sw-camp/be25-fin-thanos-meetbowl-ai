"""회의 종료/재생성 이벤트의 Rabbit 소비·발행 계약을 검증한다."""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

import aio_pika

from app.core.errors import AiError
from app.events.rabbit import AioPikaEventPublisher, MinutesEventProcessor
from app.schemas.events import EventEnvelope
from app.schemas.minutes import MinutesDraft
from app.schemas.tiptap import TiptapDocument
from app.schemas.workflow import MinutesGenerationResult


class FakeMessage:
    def __init__(self, body: bytes) -> None:
        self.body = body
        self.acked = 0
        self.requeues: list[bool] = []

    async def ack(self) -> None:
        self.acked += 1

    async def reject(self, *, requeue: bool) -> None:
        self.requeues.append(requeue)


class FakeTracker:
    def __init__(self) -> None:
        self.completed: set[UUID] = set()
        self.retry_counts: dict[UUID, int] = {}

    async def is_completed(self, event_id: UUID) -> bool:
        return event_id in self.completed

    async def mark_completed(self, event_id: UUID) -> None:
        self.completed.add(event_id)
        self.retry_counts.pop(event_id, None)

    async def increment_retry(self, event_id: UUID) -> int:
        count = self.retry_counts.get(event_id, 0) + 1
        self.retry_counts[event_id] = count
        return count


class FakePublisher:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.error = error
        self.published: list[EventEnvelope] = []

    async def publish(self, envelope: EventEnvelope) -> None:
        if self.error is not None:
            raise self.error
        self.published.append(envelope)


class FakeWorkflow:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.error = error
        self.commands: list[Any] = []

    async def execute(self, command: Any) -> MinutesGenerationResult:
        self.commands.append(command)
        if self.error is not None:
            raise self.error
        return MinutesGenerationResult(
            meeting_id=command.meeting_id,
            organization_id=command.organization_id,
            reviewer_user_id=command.reviewer_user_id,
            status="DRAFT",
            minutes_draft=MinutesDraft(
                summary="요약",
                agenda_items=[],
                decisions=["금요일 배포"],
                action_items=[],
            ),
            editor_content=TiptapDocument(type="doc", content=[]),
            model="gemini-2.5-flash",
            prompt_version="minutes-v1",
            generated_at=datetime.now(timezone.utc),
        )


class FakeExchange:
    def __init__(self) -> None:
        self.calls: list[tuple[aio_pika.Message, str]] = []

    async def publish(self, message: aio_pika.Message, routing_key: str) -> None:
        self.calls.append((message, routing_key))


def meeting_ended_event(event_id: UUID | None = None) -> EventEnvelope:
    return EventEnvelope(
        event_id=event_id or uuid4(),
        event_type="meeting.ended",
        occurred_at=datetime(2026, 6, 24, tzinfo=timezone.utc),
        producer="api-server",
        version=1,
        correlation_id=uuid4(),
        payload={
            "meetingId": str(uuid4()),
            "organizationId": str(uuid4()),
            "hostUserId": str(uuid4()),
            "reviewerUserId": str(uuid4()),
            "title": "주간 배포 회의",
            "startedAt": "2026-06-24T00:00:00Z",
            "endedAt": "2026-06-24T01:00:00Z",
        },
    )


def _processor(
    *,
    workflow: FakeWorkflow | None = None,
    publisher: FakePublisher | None = None,
    tracker: FakeTracker | None = None,
    max_retries: int = 3,
    sleep_calls: list[float] | None = None,
) -> tuple[MinutesEventProcessor, FakeTracker, FakePublisher]:
    tracker = tracker or FakeTracker()
    publisher = publisher or FakePublisher()
    workflow = workflow or FakeWorkflow()

    async def fake_sleep(delay: float) -> None:
        if sleep_calls is not None:
            sleep_calls.append(delay)

    return (
        MinutesEventProcessor(
            workflow=workflow,
            publisher=publisher,
            tracker=tracker,
            max_retries=max_retries,
            retry_delay_base_seconds=2.0,
            retry_delay_max_seconds=30.0,
            sleep=fake_sleep,
        ),
        tracker,
        publisher,
    )


def test_meeting_ended_event_is_consumed_and_minutes_generated_is_published() -> None:
    event = meeting_ended_event()
    processor, tracker, publisher = _processor()

    async def run() -> FakeMessage:
        message = FakeMessage(event.model_dump_json(by_alias=True).encode())
        await processor.process(message)
        return message

    message = asyncio.run(run())

    assert message.acked == 1
    assert message.requeues == []
    assert event.event_id in tracker.completed
    assert len(publisher.published) == 1
    assert publisher.published[0].event_type == "minutes.generated"
    assert publisher.published[0].correlation_id == event.correlation_id


def test_duplicate_minutes_event_is_acked_without_reprocessing() -> None:
    event = meeting_ended_event()
    tracker = FakeTracker()
    processor, _, publisher = _processor(tracker=tracker)

    async def run() -> tuple[FakeMessage, FakeMessage]:
        first = FakeMessage(event.model_dump_json(by_alias=True).encode())
        await processor.process(first)
        duplicate = FakeMessage(event.model_dump_json(by_alias=True).encode())
        await processor.process(duplicate)
        return first, duplicate

    first, duplicate = asyncio.run(run())

    assert first.acked == 1
    assert duplicate.acked == 1
    assert duplicate.requeues == []
    assert len(publisher.published) == 1


def test_retryable_context_failure_waits_then_requeues(caplog) -> None:
    event = meeting_ended_event()
    sleep_calls: list[float] = []
    processor, tracker, _ = _processor(
        workflow=FakeWorkflow(error=AiError("AI_CONTEXT_NOT_FOUND", "pending", retryable=True)),
        sleep_calls=sleep_calls,
    )

    with caplog.at_level(logging.ERROR, logger="uvicorn.error"):
        async def run() -> FakeMessage:
            message = FakeMessage(event.model_dump_json(by_alias=True).encode())
            await processor.process(message)
            return message

        message = asyncio.run(run())

    assert message.acked == 0
    assert message.requeues == [True]
    assert tracker.retry_counts[event.event_id] == 1
    assert sleep_calls == [2.0]
    assert str(event.event_id) in caplog.text
    assert event.payload["meetingId"] in caplog.text
    assert "code=AI_CONTEXT_NOT_FOUND" in caplog.text
    assert "retryable=True" in caplog.text


def test_publish_failure_requeues_and_does_not_mark_completed(caplog) -> None:
    event = meeting_ended_event()
    sleep_calls: list[float] = []
    processor, tracker, _ = _processor(
        publisher=FakePublisher(error=RuntimeError("unroutable")),
        sleep_calls=sleep_calls,
    )

    with caplog.at_level(logging.ERROR, logger="uvicorn.error"):
        async def run() -> FakeMessage:
            message = FakeMessage(event.model_dump_json(by_alias=True).encode())
            await processor.process(message)
            return message

        message = asyncio.run(run())

    assert message.acked == 0
    assert message.requeues == [True]
    assert event.event_id not in tracker.completed
    assert sleep_calls == [2.0]
    assert str(event.event_id) in caplog.text
    assert event.payload["meetingId"] in caplog.text
    assert "errorType=RuntimeError" in caplog.text


def test_retry_limit_sends_message_to_dlq() -> None:
    event = meeting_ended_event()
    tracker = FakeTracker()
    processor, _, _ = _processor(
        workflow=FakeWorkflow(error=RuntimeError("broker down")),
        tracker=tracker,
        max_retries=3,
    )

    requeues: list[bool] = []
    for _ in range(4):
        message = FakeMessage(event.model_dump_json(by_alias=True).encode())
        asyncio.run(processor.process(message))
        requeues.extend(message.requeues)

    assert requeues == [True, True, True, False]


def test_minutes_generated_publish_is_persistent() -> None:
    exchange = FakeExchange()
    publisher = AioPikaEventPublisher(exchange, "minutes.generated")
    envelope = meeting_ended_event().model_copy(update={"event_type": "minutes.generated"})

    asyncio.run(publisher.publish(envelope))

    message, routing_key = exchange.calls[0]
    assert routing_key == "minutes.generated"
    assert message.delivery_mode == aio_pika.DeliveryMode.PERSISTENT
    assert message.message_id == str(envelope.event_id)
    assert message.correlation_id == str(envelope.correlation_id)
