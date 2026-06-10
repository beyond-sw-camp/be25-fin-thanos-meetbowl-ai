import asyncio
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from app.core.errors import ContextNotFoundError
from app.events.idempotency import InMemoryEventTracker
from app.events.rabbit import MinutesEventProcessor
from app.providers.fake_context_loader import FakeMinutesContextLoader
from app.providers.fake_generation import FakeStructuredGenerationProvider
from app.schemas.events import EventEnvelope
from app.workflows.minutes_generation import MinutesGenerationWorkflow


class FakeMessage:
    def __init__(self, body: bytes) -> None:
        self.body = body
        self.acked = 0
        self.requeues: list[bool] = []

    async def ack(self) -> None:
        self.acked += 1

    async def reject(self, *, requeue: bool) -> None:
        self.requeues.append(requeue)


class FakePublisher:
    def __init__(self) -> None:
        self.events: list[EventEnvelope] = []

    async def publish(self, envelope: EventEnvelope) -> None:
        self.events.append(envelope)


def workflow() -> MinutesGenerationWorkflow:
    return MinutesGenerationWorkflow(
        context_loader=FakeMinutesContextLoader(),
        structured_generation_port=FakeStructuredGenerationProvider("fake"),
        model_profile="minutes-summary",
        prompt_version="minutes-v1",
    )


def meeting_ended_event(event_id: UUID | None = None) -> EventEnvelope:
    return EventEnvelope(
        event_id=event_id or uuid4(),
        event_type="meeting.ended",
        occurred_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        producer="api-server",
        version=1,
        correlation_id=uuid4(),
        payload={
            "meetingId": str(uuid4()),
            "organizationId": str(uuid4()),
            "hostUserId": str(uuid4()),
            "reviewerUserId": str(uuid4()),
            "title": "배포 회의",
            "startedAt": "2026-06-01T00:00:00Z",
            "endedAt": "2026-06-01T01:00:00Z",
        },
    )


def regeneration_event() -> EventEnvelope:
    return EventEnvelope(
        event_id=uuid4(),
        event_type="minutes.generation.requested",
        occurred_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        producer="api-server",
        version=1,
        correlation_id=uuid4(),
        payload={
            "meetingId": str(uuid4()),
            "organizationId": str(uuid4()),
            "requestedByUserId": str(uuid4()),
            "reviewerUserId": str(uuid4()),
            "reason": "MANUAL_REGENERATE",
            "promptVersion": "minutes-v1",
        },
    )


def processor(publisher: FakePublisher, tracker: InMemoryEventTracker) -> MinutesEventProcessor:
    return MinutesEventProcessor(
        workflow=workflow(), publisher=publisher, tracker=tracker, max_retries=3
    )


def test_success_publishes_generated_event_then_acks() -> None:
    publisher = FakePublisher()
    event = meeting_ended_event()
    message = FakeMessage(event.model_dump_json(by_alias=True).encode())

    asyncio.run(processor(publisher, InMemoryEventTracker()).process(message))

    assert message.acked == 1
    assert publisher.events[0].event_type == "minutes.generated"
    assert publisher.events[0].correlation_id == event.correlation_id
    assert publisher.events[0].event_id != event.event_id
    # editorContent is intentionally excluded until the root event contract is updated.
    assert "editorContent" not in publisher.events[0].payload


def test_regeneration_event_uses_same_workflow() -> None:
    publisher = FakePublisher()
    event = regeneration_event()
    message = FakeMessage(event.model_dump_json(by_alias=True).encode())

    asyncio.run(processor(publisher, InMemoryEventTracker()).process(message))

    assert message.acked == 1
    assert publisher.events[0].payload["promptVersion"] == "minutes-v1"


def test_duplicate_event_is_acked_without_republish() -> None:
    publisher = FakePublisher()
    tracker = InMemoryEventTracker()
    event = meeting_ended_event()
    service = processor(publisher, tracker)

    asyncio.run(service.process(FakeMessage(event.model_dump_json(by_alias=True).encode())))
    duplicate = FakeMessage(event.model_dump_json(by_alias=True).encode())
    asyncio.run(service.process(duplicate))

    assert duplicate.acked == 1
    assert len(publisher.events) == 1


def test_invalid_message_is_rejected_to_dlq() -> None:
    message = FakeMessage(b"not-json")

    asyncio.run(processor(FakePublisher(), InMemoryEventTracker()).process(message))

    assert message.requeues == [False]


def test_unsupported_event_is_rejected_to_dlq() -> None:
    event = meeting_ended_event().model_copy(update={"event_type": "meeting.unknown"})
    message = FakeMessage(event.model_dump_json(by_alias=True).encode())

    asyncio.run(processor(FakePublisher(), InMemoryEventTracker()).process(message))

    assert message.requeues == [False]


def test_retryable_failure_requeues_three_times_then_rejects() -> None:
    class MissingContextWorkflow:
        async def execute(self, _: Any) -> Any:
            raise ContextNotFoundError()

    service = MinutesEventProcessor(
        workflow=MissingContextWorkflow(),
        publisher=FakePublisher(),
        tracker=InMemoryEventTracker(),
        max_retries=3,
    )
    event = meeting_ended_event()
    requeues: list[bool] = []

    for _ in range(4):
        message = FakeMessage(event.model_dump_json(by_alias=True).encode())
        asyncio.run(service.process(message))
        requeues.extend(message.requeues)

    assert requeues == [True, True, True, False]
