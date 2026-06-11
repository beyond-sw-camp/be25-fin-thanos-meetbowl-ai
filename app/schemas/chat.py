from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from app.schemas.base import ApiModel


ChatSourceType = Literal[
    "BACKUP_MAIL",
    "MINUTES",
    "PERSONAL_MEMO",
    "PERSONAL_DRIVE_FILE",
    "SHARED_WORKSPACE_FILE_VERSION",
]


class ChatMessage(ApiModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=20_000)


class ChatRequest(ApiModel):
    request_id: UUID
    correlation_id: UUID
    user_id: UUID
    organization_id: UUID
    question: str = Field(min_length=1, max_length=20_000)
    message_history: list[ChatMessage] = Field(default_factory=list, max_length=20)
    shared_workspace_ids: list[UUID] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_history(self) -> "ChatRequest":
        if self.message_history and self.message_history[0].role != "user":
            raise ValueError("messageHistory must start with user")
        if self.message_history and self.message_history[-1].role != "assistant":
            raise ValueError("messageHistory must end with assistant")
        for previous, current in zip(
            self.message_history, self.message_history[1:], strict=False
        ):
            if previous.role == current.role:
                raise ValueError("messageHistory roles must alternate")
        if sum(len(message.content) for message in self.message_history) > 40_000:
            raise ValueError("messageHistory content is too long")
        return self


class ChatSource(ApiModel):
    type: ChatSourceType
    resource_id: UUID
    title: str = Field(min_length=1, max_length=255)
    snippet: str = Field(min_length=1, max_length=2_000)
    score: float = Field(ge=0.0, le=1.0)


class ChatResult(ApiModel):
    answer: str = Field(min_length=1, max_length=20_000)
    sources: list[ChatSource] = Field(default_factory=list, max_length=20)
    model: str = Field(min_length=1, max_length=100)
    prompt_version: str = Field(min_length=1, max_length=50)


class ChatSuccessResponse(ApiModel):
    success: bool = True
    data: ChatResult
    message: str | None = None


class GeneratedChatAnswer(ApiModel):
    answer: str = Field(min_length=1, max_length=20_000)
