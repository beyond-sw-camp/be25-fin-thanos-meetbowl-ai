from datetime import datetime
from typing import Any

from pydantic import Field
from uuid import UUID

from app.schemas.base import UtcDatetimeModel
from app.schemas.minutes import Participant
from app.schemas.workflow import MinutesGenerationResult


class GenerateMinutesRequest(UtcDatetimeModel):
    meeting_id: UUID
    organization_id: UUID
    host_user_id: UUID
    reviewer_user_id: UUID
    title: str
    started_at: datetime
    ended_at: datetime
    participants: list[Participant]
    raw_transcript: str


class SuccessResponse(UtcDatetimeModel):
    success: bool = True
    data: MinutesGenerationResult
    message: str | None = None


class ErrorBody(UtcDatetimeModel):
    code: str
    message: str
    details: list[Any] = Field(default_factory=list)


class FailureResponse(UtcDatetimeModel):
    success: bool = False
    error: ErrorBody
