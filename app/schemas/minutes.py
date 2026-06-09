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


class ActionItem(ApiModel):
    content: str = Field(min_length=1)
    assignee_name: str | None = None
    due_date: date | None = None


class MinutesDraft(ApiModel):
    summary: str = Field(min_length=1)
    agenda_items: list[AgendaItem] = Field(default_factory=list)
    decisions: list[str] = Field(default_factory=list)
    action_items: list[ActionItem] = Field(default_factory=list)
