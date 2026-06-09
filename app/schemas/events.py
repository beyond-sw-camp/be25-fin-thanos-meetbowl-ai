from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import Field

from app.schemas.base import UtcDatetimeModel
from app.schemas.minutes import ActionItem, AgendaItem


class EventEnvelope(UtcDatetimeModel):
    event_id: UUID
    event_type: str = Field(min_length=1)
    occurred_at: datetime
    producer: str = Field(min_length=1)
    version: Literal[1]
    correlation_id: UUID
    payload: dict[str, Any]


class MeetingEndedPayload(UtcDatetimeModel):
    meeting_id: UUID
    organization_id: UUID
    host_user_id: UUID
    reviewer_user_id: UUID
    title: str
    started_at: datetime
    ended_at: datetime


class MinutesGenerationRequestedPayload(UtcDatetimeModel):
    meeting_id: UUID
    organization_id: UUID
    requested_by_user_id: UUID
    reviewer_user_id: UUID
    reason: str
    prompt_version: str


class MinutesGeneratedPayload(UtcDatetimeModel):
    meeting_id: UUID
    reviewer_user_id: UUID
    status: Literal["DRAFT"]
    summary: str
    agenda_items: list[AgendaItem]
    decisions: list[str]
    action_items: list[ActionItem]
    model: str
    prompt_version: str
