from datetime import datetime
from uuid import UUID

from pydantic import Field

from app.schemas.base import UtcDatetimeModel
from app.schemas.minutes import MinutesDraft, Participant
from app.schemas.tiptap import TiptapDocument


class MinutesGenerationCommand(UtcDatetimeModel):
    meeting_id: UUID
    organization_id: UUID
    reviewer_user_id: UUID
    host_user_id: UUID | None = None
    requested_by_user_id: UUID | None = None
    title: str | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None
    prompt_version: str | None = None
    reason: str | None = None
    participants: list[Participant] | None = None
    raw_transcript: str | None = None


class MinutesGenerationContext(UtcDatetimeModel):
    meeting_id: UUID
    organization_id: UUID
    host_user_id: UUID
    reviewer_user_id: UUID
    title: str = Field(min_length=1)
    started_at: datetime
    ended_at: datetime
    participants: list[Participant] = Field(default_factory=list)
    # 회의 원문의 외부 전달 형식과 생성 파이프라인을 분리하기 위한 정규화 경계다.
    raw_transcript: str = ""


class MinutesGenerationResult(UtcDatetimeModel):
    meeting_id: UUID
    organization_id: UUID
    reviewer_user_id: UUID
    status: str = Field(pattern="^DRAFT$")
    minutes_draft: MinutesDraft
    editor_content: TiptapDocument
    model: str
    prompt_version: str
    generated_at: datetime
