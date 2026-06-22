from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from app.schemas.base import ApiModel, UtcDatetimeModel


FeedbackType = Literal[
    "DECISION_REMINDER",
    "DUPLICATE_DISCUSSION",
    "RESOLVED_TOPIC",
]


class FeedbackTranscriptSegment(ApiModel):
    segment_id: UUID
    sequence: int = Field(ge=0)
    language: str = Field(min_length=1, max_length=20)
    text: str = Field(min_length=1, max_length=4_000)
    is_final: bool = True
    started_at_ms: int = Field(ge=0)
    ended_at_ms: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_time_range(self) -> "FeedbackTranscriptSegment":
        if self.ended_at_ms < self.started_at_ms:
            raise ValueError("endedAtMs must be greater than or equal to startedAtMs")
        return self


class FeedbackCandidate(ApiModel):
    minutes_id: UUID
    meeting_id: UUID | None = None
    title: str = Field(min_length=1, max_length=255)
    meeting_date: str = Field(min_length=1, max_length=10)
    snippet: str = Field(min_length=1, max_length=2_000)
    score: float = Field(ge=0.0, le=1.0)


class MeetingFeedbackCommand(ApiModel):
    meeting_id: UUID
    session_id: UUID
    organization_id: UUID
    participant_user_ids: list[UUID] = Field(default_factory=list, min_length=1)
    correlation_id: UUID
    transcript_window: list[FeedbackTranscriptSegment] = Field(
        default_factory=list, min_length=1
    )


class MeetingFeedbackResult(UtcDatetimeModel):
    feedback_id: UUID
    meeting_id: UUID
    session_id: UUID
    feedback_type: FeedbackType
    message: str = Field(min_length=1, max_length=500)
    sources: list[FeedbackCandidate] = Field(default_factory=list, min_length=1)
    audience_user_ids: list[UUID] = Field(default_factory=list, min_length=1)
    from_sequence: int = Field(ge=0)
    to_sequence: int = Field(ge=0)
    generated_at: datetime

    @model_validator(mode="after")
    def validate_sequence_range(self) -> "MeetingFeedbackResult":
        if self.to_sequence < self.from_sequence:
            raise ValueError("toSequence must be greater than or equal to fromSequence")
        return self
