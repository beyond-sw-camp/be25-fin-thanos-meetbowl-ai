import asyncio
from datetime import datetime, timezone
from uuid import UUID, uuid4

from app.core.errors import DocumentIndexFailedError
from app.events.idempotency import InMemoryEventTracker
from app.events.rabbit import DocumentIndexEventProcessor
from app.schemas.events import EventEnvelope


class FakeMessage:
    def __init__(self, body: bytes) -> None:
        self.body = body
        self.acked = 0
        self.requeues: list[bool] = []

    async def ack(self) -> None:
        self.acked += 1

    async def reject(self, *, requeue: bool) -> None:
        self.requeues.append(requeue)


class CapturingWorkflow:
    def __init__(self) -> None:
        self.commands = []

    async def execute(self, command: object) -> object:
        self.commands.append(command)
        return object()


def index_event(event_id: UUID | None = None) -> EventEnvelope:
    return EventEnvelope(
        event_id=event_id or uuid4(),
        event_type="document.index.requested",
        occurred_at=datetime(2026, 6, 12, tzinfo=timezone.utc),
        producer="api-server",
        version=1,
        correlation_id=uuid4(),
        payload={
            "documentId": str(uuid4()),
            "documentType": "MEETING_MINUTES",
            "organizationId": str(uuid4()),
            "ownerUserId": str(uuid4()),
            "title": "회의록",
            "content": "임베딩할 회의록 본문입니다.",
            "metadata": {
                "meetingId": str(uuid4()),
                "approvedAt": "2026-06-12T00:00:00Z"
            },
            "accessScope": {
                "userIds": [str(uuid4())],
                "departmentIds": [],
                "sharedWorkspaceIds": [],
            },
        },
    )


def test_document_index_event_is_acked_on_success() -> None:
    workflow = CapturingWorkflow()
    processor = DocumentIndexEventProcessor(
        workflow=workflow,
        tracker=InMemoryEventTracker(),
        max_retries=3,
    )
    event = index_event()
    message = FakeMessage(event.model_dump_json(by_alias=True).encode())

    asyncio.run(processor.process(message))

    assert message.acked == 1
    assert len(workflow.commands) == 1
    assert workflow.commands[0].created_at == event.occurred_at
    assert workflow.commands[0].metadata.meeting_id is not None


def test_duplicate_document_index_event_is_acked_without_reprocessing() -> None:
    tracker = InMemoryEventTracker()
    workflow = CapturingWorkflow()
    processor = DocumentIndexEventProcessor(
        workflow=workflow,
        tracker=tracker,
        max_retries=3,
    )
    event = index_event()

    asyncio.run(processor.process(FakeMessage(event.model_dump_json(by_alias=True).encode())))
    duplicate = FakeMessage(event.model_dump_json(by_alias=True).encode())
    asyncio.run(processor.process(duplicate))

    assert duplicate.acked == 1
    assert len(workflow.commands) == 1


def test_retryable_document_index_failure_requeues_then_dlqs() -> None:
    class FailingWorkflow:
        async def execute(self, _: object) -> object:
            raise DocumentIndexFailedError()

    processor = DocumentIndexEventProcessor(
        workflow=FailingWorkflow(),
        tracker=InMemoryEventTracker(),
        max_retries=2,
    )
    event = index_event()
    outcomes: list[bool] = []

    for _ in range(3):
        message = FakeMessage(event.model_dump_json(by_alias=True).encode())
        asyncio.run(processor.process(message))
        outcomes.extend(message.requeues)

    assert outcomes == [True, True, False]
