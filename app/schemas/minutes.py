from datetime import date
from uuid import UUID

from pydantic import Field

from app.schemas.base import ApiModel


class Participant(ApiModel):
    user_id: UUID
    name: str = Field(min_length=1)
    department: str | None = None


class AgendaItem(ApiModel):
    title: str = Field(min_length=1)
    discussion: str = Field(min_length=1)
    decision: str | None = None


class TranscriptSegment(ApiModel):
    segment_id: str | None = None
    sequence: int = Field(ge=1)
    language: str | None = None
    source_text: str = Field(min_length=1)
    started_at_ms: int | None = None
    ended_at_ms: int | None = None
    suspicious: bool = False


class EvidenceDecision(ApiModel):
    content: str = Field(min_length=1)
    source_sequences: list[int] = Field(default_factory=list)


class EvidenceActionItem(ApiModel):
    content: str = Field(min_length=1)
    assignee_name: str | None = None
    due_date: date | None = None
    source_sequences: list[int] = Field(default_factory=list)


class EvidenceAgendaItem(ApiModel):
    title: str = Field(min_length=1)
    discussion_points: list[str] = Field(default_factory=list)
    source_sequences: list[int] = Field(default_factory=list)
    decision: str | None = None


class MinutesEvidence(ApiModel):
    summary: str = Field(min_length=1)
    agenda_items: list[EvidenceAgendaItem] = Field(default_factory=list)
    decisions: list[EvidenceDecision] = Field(default_factory=list)
    action_items: list[EvidenceActionItem] = Field(default_factory=list)


class ActionItem(ApiModel):
    content: str = Field(min_length=1)
    assignee_name: str | None = None
    due_date: date | None = None


class MinutesDraft(ApiModel):
    summary: str = Field(min_length=1)
    agenda_items: list[AgendaItem] = Field(default_factory=list)
    decisions: list[str] = Field(default_factory=list)
    action_items: list[ActionItem] = Field(default_factory=list)
