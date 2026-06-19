import asyncio
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from app.consumers.redis_feedback import FeedbackEventProcessor
from app.schemas.events import EventEnvelope, MeetingFeedbackGeneratedPayload
from app.schemas.feedback import (
    FeedbackCandidate,
    MeetingFeedbackCommand,
    MeetingFeedbackResult,
)


class RecordingWorkflow:
    def __init__(self) -> None:
        self.commands: list[MeetingFeedbackCommand] = []

    async def execute(self, command: MeetingFeedbackCommand):
        self.commands.append(command)
        return None


class ResultWorkflow:
    def __init__(self) -> None:
        self.commands: list[MeetingFeedbackCommand] = []
        self.source_minutes_id = uuid4()

    async def execute(
        self, command: MeetingFeedbackCommand
    ) -> MeetingFeedbackResult:
        self.commands.append(command)
        return MeetingFeedbackResult(
            feedback_id=uuid4(),
            meeting_id=command.meeting_id,
            session_id=command.session_id,
            feedback_type="DUPLICATE_DISCUSSION",
            message="이전에 유사한 논의가 있었습니다.",
            sources=[
                FeedbackCandidate(
                    minutes_id=self.source_minutes_id,
                    meeting_id=uuid4(),
                    title="과거 회의록",
                    meeting_date="2026-06-10",
                    snippet="결제 승인 정책을 검토했습니다.",
                    score=0.9,
                )
            ],
            audience_user_ids=command.participant_user_ids,
            from_sequence=command.transcript_window[0].sequence,
            to_sequence=command.transcript_window[-1].sequence,
            generated_at=datetime(2026, 6, 19, tzinfo=timezone.utc),
        )


class RecordingPublisher:
    def __init__(self) -> None:
        self.published: list[tuple[MeetingFeedbackGeneratedPayload, UUID]] = []

    async def publish(
        self,
        *,
        result_payload: MeetingFeedbackGeneratedPayload,
        correlation_id: UUID,
    ) -> None:
        self.published.append((result_payload, correlation_id))


class MutableClock:
    def __init__(self) -> None:
        self.current = datetime(2026, 6, 19, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.current

    def advance(self, seconds: int) -> None:
        self.current += timedelta(seconds=seconds)


def _processor(
    workflow,
    *,
    publisher: RecordingPublisher | None = None,
    min_segments: int = 1,
    state_ttl_seconds: int = 300,
    clock: MutableClock | None = None,
) -> FeedbackEventProcessor:
    return FeedbackEventProcessor(
        workflow=workflow,
        publisher=publisher,
        max_segments=8,
        max_window_seconds=45,
        min_segments=min_segments,
        min_window_chars=1,
        trigger_interval_seconds=0,
        cooldown_seconds=90,
        state_ttl_seconds=state_ttl_seconds,
        clock=clock,
    )


def _event(
    *,
    meeting_id: UUID,
    session_id: UUID,
    sequence: int,
    segment_id: UUID | None = None,
    participant_user_ids: list[UUID] | None = None,
    is_final: bool = True,
) -> str:
    envelope = EventEnvelope(
        event_id=uuid4(),
        event_type="meeting.feedback.segment.created",
        occurred_at=datetime(2026, 6, 19, tzinfo=timezone.utc),
        producer="stt-server",
        version=1,
        correlation_id=uuid4(),
        payload={
            "meetingId": str(meeting_id),
            "sessionId": str(session_id),
            "organizationId": str(uuid4()),
            "participantUserIds": [
                str(value) for value in (participant_user_ids or [uuid4()])
            ],
            "segmentId": str(segment_id or uuid4()),
            "sequence": sequence,
            "language": "ko",
            "text": f"segment-{sequence}",
            "isFinal": is_final,
            "startedAtMs": sequence * 1_000,
            "endedAtMs": sequence * 1_000 + 500,
        },
    )
    return envelope.model_dump_json(by_alias=True)


def test_windows_are_isolated_by_meeting_and_session() -> None:
    workflow = RecordingWorkflow()
    processor = _processor(workflow, min_segments=2)
    meeting_id = uuid4()
    session_a = uuid4()
    session_b = uuid4()

    async def run() -> None:
        await processor.process_raw(
            _event(meeting_id=meeting_id, session_id=session_a, sequence=0)
        )
        await processor.process_raw(
            _event(meeting_id=meeting_id, session_id=session_b, sequence=0)
        )
        await processor.process_raw(
            _event(meeting_id=meeting_id, session_id=session_a, sequence=1)
        )
        await processor.process_raw(
            _event(meeting_id=meeting_id, session_id=session_b, sequence=1)
        )

    asyncio.run(run())

    assert [command.session_id for command in workflow.commands] == [session_a, session_b]
    assert [
        [segment.sequence for segment in command.transcript_window]
        for command in workflow.commands
    ] == [[0, 1], [0, 1]]


def test_duplicate_and_out_of_order_segments_are_ignored() -> None:
    workflow = RecordingWorkflow()
    processor = _processor(workflow)
    meeting_id = uuid4()
    session_id = uuid4()
    first_segment_id = uuid4()
    latest_participant = uuid4()

    async def run() -> None:
        first = _event(
            meeting_id=meeting_id,
            session_id=session_id,
            sequence=1,
            segment_id=first_segment_id,
        )
        await processor.process_raw(first)
        await processor.process_raw(first)
        await processor.process_raw(
            _event(meeting_id=meeting_id, session_id=session_id, sequence=0)
        )
        await processor.process_raw(
            _event(
                meeting_id=meeting_id,
                session_id=session_id,
                sequence=2,
                participant_user_ids=[latest_participant],
            )
        )

    asyncio.run(run())

    assert len(workflow.commands) == 2
    assert [segment.sequence for segment in workflow.commands[-1].transcript_window] == [1, 2]
    assert workflow.commands[-1].participant_user_ids == [latest_participant]


def test_non_final_segments_are_ignored() -> None:
    workflow = RecordingWorkflow()
    processor = _processor(workflow)

    asyncio.run(
        processor.process_raw(
            _event(
                meeting_id=uuid4(),
                session_id=uuid4(),
                sequence=0,
                is_final=False,
            )
        )
    )

    assert workflow.commands == []


def test_expired_session_windows_are_removed() -> None:
    workflow = RecordingWorkflow()
    clock = MutableClock()
    processor = _processor(
        workflow, min_segments=10, state_ttl_seconds=10, clock=clock
    )
    meeting_id = uuid4()
    first_session = uuid4()

    async def run() -> None:
        await processor.process_raw(
            _event(meeting_id=meeting_id, session_id=first_session, sequence=0)
        )

    asyncio.run(run())
    clock.advance(10)
    processor.cleanup_expired_state()

    assert processor._windows == {}


def test_none_result_does_not_publish_feedback() -> None:
    workflow = RecordingWorkflow()
    publisher = RecordingPublisher()
    processor = _processor(workflow, publisher=publisher)

    asyncio.run(
        processor.process_raw(
            _event(meeting_id=uuid4(), session_id=uuid4(), sequence=0)
        )
    )

    assert len(workflow.commands) == 1
    assert publisher.published == []


def test_success_result_publishes_delivery_scope() -> None:
    workflow = ResultWorkflow()
    publisher = RecordingPublisher()
    processor = _processor(workflow, publisher=publisher)
    meeting_id = uuid4()
    session_id = uuid4()
    participant_user_id = uuid4()

    asyncio.run(
        processor.process_raw(
            _event(
                meeting_id=meeting_id,
                session_id=session_id,
                sequence=7,
                participant_user_ids=[participant_user_id],
            )
        )
    )

    assert len(publisher.published) == 1
    payload, _ = publisher.published[0]
    assert payload.meeting_id == meeting_id
    assert payload.session_id == session_id
    assert payload.audience_user_ids == [participant_user_id]
    assert payload.from_sequence == 7
    assert payload.to_sequence == 7


def test_cooldown_suppresses_same_feedback_source_in_a_session() -> None:
    workflow = ResultWorkflow()
    publisher = RecordingPublisher()
    clock = MutableClock()
    processor = _processor(workflow, publisher=publisher, clock=clock)
    meeting_id = uuid4()
    session_id = uuid4()

    async def run() -> None:
        await processor.process_raw(
            _event(meeting_id=meeting_id, session_id=session_id, sequence=0)
        )
        clock.advance(1)
        await processor.process_raw(
            _event(meeting_id=meeting_id, session_id=session_id, sequence=1)
        )

    asyncio.run(run())

    assert len(workflow.commands) == 2
    assert len(publisher.published) == 1
