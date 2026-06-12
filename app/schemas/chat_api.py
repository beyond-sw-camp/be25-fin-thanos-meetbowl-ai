from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from app.schemas.base import ApiModel
from app.schemas.chat import ChatSourceType


class BeChatMessageRequest(ApiModel):
    """BE가 전달하는 직전 대화 한 턴(사용자/어시스턴트 메시지)."""

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=20_000)


class BeChatRequest(ApiModel):
    """BE 서버가 AI 챗봇으로 보내는 요청 계약(외부 통신용 DTO)."""

    request_id: UUID
    correlation_id: UUID
    user_id: UUID
    organization_id: UUID
    question: str = Field(min_length=1, max_length=20_000)
    message_history: list[BeChatMessageRequest] = Field(default_factory=list, max_length=20)
    shared_workspace_ids: list[UUID] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_history(self) -> "BeChatRequest":
        # 대화 이력은 user로 시작해 assistant로 끝나고 역할이 번갈아 나와야 한다.
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


class BeChatSourceResponse(ApiModel):
    """챗봇 답변의 근거가 된 출처 한 건(자료 유형, 식별자, 유사도 점수 등)."""

    type: ChatSourceType
    resource_id: UUID
    title: str
    snippet: str
    score: float


class BeChatDataResponse(ApiModel):
    """BE가 소비하는 응답 본문(답변, 출처 목록, 사용 모델 정보)."""

    answer: str
    sources: list[BeChatSourceResponse]
    model: str
    prompt_version: str


class BeChatSuccessResponse(ApiModel):
    """BE 서버로 돌려주는 챗봇 성공 응답 계약(외부 통신용 DTO)."""

    success: bool = True
    data: BeChatDataResponse
    message: str | None = None
