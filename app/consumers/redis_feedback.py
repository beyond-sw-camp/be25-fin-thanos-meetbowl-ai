import asyncio
import logging
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Protocol
from uuid import UUID, uuid4

from pydantic import ValidationError

from app.schemas.events import (
    EventEnvelope,
    FeedbackSegmentCreatedPayload,
    MeetingFeedbackGeneratedPayload,
)
from app.schemas.feedback import FeedbackTranscriptSegment, MeetingFeedbackCommand
from app.workflows.meeting_feedback import MeetingFeedbackWorkflow

logger = logging.getLogger(__name__)

FEEDBACK_SEGMENT_CREATED = "meeting.feedback.segment.created"
FEEDBACK_GENERATED = "meeting.feedback.generated"


class FeedbackResultPublisher(Protocol):
    async def publish(
        self, *, result_payload: MeetingFeedbackGeneratedPayload, correlation_id: UUID
    ) -> None: ...


@dataclass
class MeetingWindowState:
    segments: deque[FeedbackTranscriptSegment]
    last_query_ended_at_ms: int | None = None
    last_query_fingerprint: str | None = None


class FeedbackEventProcessor:
    def __init__(
        self,
        *,
        workflow: MeetingFeedbackWorkflow,
        publisher: FeedbackResultPublisher | None,
        max_segments: int,
        max_window_seconds: int,
        min_segments: int,
        min_window_chars: int,
        trigger_interval_seconds: int,
        cooldown_seconds: int,
    ) -> None:
        self._workflow = workflow
        self._publisher = publisher
        self._max_segments = max_segments
        self._max_window_seconds = max_window_seconds
        self._min_segments = min_segments
        self._min_window_chars = min_window_chars
        self._trigger_interval_ms = trigger_interval_seconds * 1000
        self._cooldown_seconds = cooldown_seconds
        self._windows: dict[UUID, MeetingWindowState] = {}
        self._last_published_at: dict[tuple[str, str, tuple[str, ...]], datetime] = {}

    def set_publisher(self, publisher: FeedbackResultPublisher) -> None:
        self._publisher = publisher

    async def process_raw(self, raw_event: str) -> None:
        try:
            envelope = EventEnvelope.model_validate_json(raw_event)
            if envelope.event_type != FEEDBACK_SEGMENT_CREATED:
                return
            payload = FeedbackSegmentCreatedPayload.model_validate(envelope.payload)
        except ValidationError:
            return

        state = self._windows.setdefault(
            payload.meeting_id,
            MeetingWindowState(segments=deque(maxlen=self._max_segments)),
        )
        state.segments.append(
            FeedbackTranscriptSegment(
                segment_id=payload.segment_id,
                sequence=payload.sequence,
                language=payload.language,
                text=payload.text,
                is_final=payload.is_final,
                started_at_ms=payload.started_at_ms,
                ended_at_ms=payload.ended_at_ms,
            )
        )
        _trim_expired_segments(state.segments, payload.ended_at_ms, self._max_window_seconds)
        if len(state.segments) < self._min_segments:
            return
        if sum(len(segment.text) for segment in state.segments) < self._min_window_chars:
            return
        if (
            state.last_query_ended_at_ms is not None
            and payload.ended_at_ms - state.last_query_ended_at_ms < self._trigger_interval_ms
        ):
            return
        fingerprint = _build_window_fingerprint(state.segments)
        if fingerprint == state.last_query_fingerprint:
            return
        try:
            result = await self._workflow.execute(
                MeetingFeedbackCommand(
                    meeting_id=payload.meeting_id,
                    session_id=payload.session_id,
                    organization_id=payload.organization_id,
                    participant_user_ids=payload.participant_user_ids,
                    correlation_id=envelope.correlation_id,
                    transcript_window=list(state.segments),
                )
            )
        except Exception as exc:
            logger.warning("meeting feedback workflow failed: %s", exc)
            return
        state.last_query_ended_at_ms = payload.ended_at_ms
        state.last_query_fingerprint = fingerprint
        if result is None:
            return
        dedupe_key = (
            str(result.meeting_id),
            result.feedback_type,
            tuple(str(source.minutes_id) for source in result.sources),
        )
        last_published_at = self._last_published_at.get(dedupe_key)
        if last_published_at is not None and (
            result.generated_at - last_published_at
        ) < timedelta(seconds=self._cooldown_seconds):
            return
        payload = MeetingFeedbackGeneratedPayload(
            meeting_id=result.meeting_id,
            feedback_type=result.feedback_type,
            message=result.message,
            sources=result.sources,
            generated_at=result.generated_at,
        )
        if self._publisher is None:
            return
        await self._publisher.publish(
            result_payload=payload,
            correlation_id=envelope.correlation_id,
        )
        self._last_published_at[dedupe_key] = result.generated_at


class RedisFeedbackRuntime(FeedbackResultPublisher):
    def __init__(
        self,
        *,
        redis_url: str,
        consumer_group: str,
        consumer_name: str,
        stream_max_length: int,
        scan_interval_seconds: float,
        processor: FeedbackEventProcessor,
    ) -> None:
        self._redis_url = redis_url
        self._consumer_group = consumer_group
        self._consumer_name = consumer_name
        self._stream_max_length = stream_max_length
        self._scan_interval_seconds = scan_interval_seconds
        self._processor = processor
        self._task: asyncio.Task[None] | None = None
        self._client = None

    async def start(self) -> None:
        from redis.asyncio import Redis

        self._client = Redis.from_url(self._redis_url, decode_responses=True)
        await self._client.ping()
        self._task = asyncio.create_task(self._consume_loop())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def publish(
        self, *, result_payload: MeetingFeedbackGeneratedPayload, correlation_id: UUID
    ) -> None:
        if self._client is None:
            return
        envelope = EventEnvelope(
            event_id=uuid4(),
            event_type=FEEDBACK_GENERATED,
            occurred_at=datetime.now(timezone.utc),
            producer="ai-server",
            version=1,
            correlation_id=correlation_id,
            payload=result_payload.model_dump(mode="json", by_alias=True),
        )
        await self._client.xadd(
            f"meeting:{result_payload.meeting_id}:feedback-result",
            {"event": envelope.model_dump_json(by_alias=True)},
            maxlen=self._stream_max_length,
            approximate=True,
        )

    async def _consume_loop(self) -> None:
        assert self._client is not None
        known_streams: set[str] = set()
        while True:
            try:
                discovered_streams = await self._discover_streams()
                for stream in discovered_streams - known_streams:
                    await self._ensure_group(stream)
                known_streams |= discovered_streams
                if not known_streams:
                    await asyncio.sleep(self._scan_interval_seconds)
                    continue
                response = await self._client.xreadgroup(
                    groupname=self._consumer_group,
                    consumername=self._consumer_name,
                    streams={stream: ">" for stream in sorted(known_streams)},
                    count=10,
                    block=1000,
                )
                for stream_name, messages in response or []:
                    for message_id, fields in messages:
                        raw_event = fields.get("event")
                        if raw_event:
                            await self._processor.process_raw(raw_event)
                        await self._client.xack(stream_name, self._consumer_group, message_id)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("redis feedback runtime loop failed: %s", exc)
                await asyncio.sleep(self._scan_interval_seconds)

    async def _discover_streams(self) -> set[str]:
        assert self._client is not None
        cursor = 0
        streams: set[str] = set()
        while True:
            cursor, keys = await self._client.scan(
                cursor=cursor, match="meeting:*:feedback-source", count=100
            )
            streams.update(keys)
            if cursor == 0:
                break
        return streams

    async def _ensure_group(self, stream: str) -> None:
        assert self._client is not None
        try:
            await self._client.xgroup_create(
                name=stream,
                groupname=self._consumer_group,
                id="0",
                mkstream=True,
            )
        except Exception as exc:
            if "BUSYGROUP" not in str(exc):
                raise


def _trim_expired_segments(
    segments: deque[FeedbackTranscriptSegment], latest_ended_at_ms: int, max_window_seconds: int
) -> None:
    min_started_at_ms = latest_ended_at_ms - (max_window_seconds * 1000)
    while segments and segments[0].ended_at_ms < min_started_at_ms:
        segments.popleft()


def _build_window_fingerprint(segments: deque[FeedbackTranscriptSegment]) -> str:
    return "|".join(
        f"{segment.sequence}:{segment.text.strip().lower()}" for segment in segments
    )
