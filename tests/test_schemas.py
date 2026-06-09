from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.events import EventEnvelope
from app.schemas.minutes import MinutesDraft


def test_event_envelope_accepts_valid_contract() -> None:
    envelope = EventEnvelope(
        eventId=uuid4(),
        eventType="meeting.ended",
        occurredAt="2026-06-01T03:00:00Z",
        producer="api-server",
        version=1,
        correlationId=uuid4(),
        payload={},
    )

    assert envelope.occurred_at == datetime(2026, 6, 1, 3, 0, tzinfo=timezone.utc)


def test_event_envelope_rejects_non_utc_datetime() -> None:
    with pytest.raises(ValidationError):
        EventEnvelope(
            eventId=uuid4(),
            eventType="meeting.ended",
            occurredAt="2026-06-01T12:00:00+09:00",
            producer="api-server",
            version=1,
            correlationId=uuid4(),
            payload={},
        )


def test_minutes_draft_allows_empty_decisions_and_action_items() -> None:
    draft = MinutesDraft(summary="요약", agendaItems=[], decisions=[], actionItems=[])

    assert draft.decisions == []
    assert draft.action_items == []
