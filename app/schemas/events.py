from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import Field

from app.schemas.base import UtcDatetimeModel
from app.schemas.feedback import FeedbackCandidate
from app.schemas.indexing import AccessScope, DocumentMetadata
from app.schemas.minutes import ActionItem, AgendaItem
from app.schemas.tiptap import TiptapDocument


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
    organization_id: UUID
    reviewer_user_id: UUID
    status: Literal["DRAFT"]
    summary: str
    agenda_items: list[AgendaItem]
    decisions: list[str]
    action_items: list[ActionItem]
    editor_content: TiptapDocument
    model: str
    prompt_version: str


class DocumentIndexRequestedPayload(UtcDatetimeModel):
    document_id: UUID
    document_type: str = Field(min_length=1)
    organization_id: UUID
    owner_user_id: UUID
    title: str = Field(min_length=1)
    content: str = Field(min_length=1)
    metadata: DocumentMetadata = Field(default_factory=DocumentMetadata)
    access_scope: AccessScope


class FeedbackSegmentCreatedPayload(UtcDatetimeModel):
    meeting_id: UUID
    session_id: UUID
    organization_id: UUID
    participant_user_ids: list[UUID] = Field(default_factory=list, min_length=1)
    segment_id: UUID
    sequence: int = Field(ge=0)
    language: str = Field(min_length=1, max_length=20)
    text: str = Field(min_length=1, max_length=4_000)
    is_final: bool = True
    started_at_ms: int = Field(ge=0)
    ended_at_ms: int = Field(ge=0)


class MeetingFeedbackGeneratedPayload(UtcDatetimeModel):
    meeting_id: UUID
    feedback_type: str = Field(min_length=1, max_length=50)
    message: str = Field(min_length=1, max_length=500)
    sources: list[FeedbackCandidate] = Field(default_factory=list)
    generated_at: datetime
