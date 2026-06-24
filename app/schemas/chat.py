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


class ChatCommand(ApiModel):
    request_id: UUID
    correlation_id: UUID
    user_id: UUID
    # 검색 권한은 소유자/워크스페이스로만 판정하므로 조직 미소속 사용자(organization 없음)도 질의할 수 있다.
    organization_id: UUID | None = None
    question: str = Field(min_length=1, max_length=20_000)
    message_history: list[ChatMessage] = Field(default_factory=list, max_length=20)
    shared_workspace_ids: list[UUID] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_history(self) -> "ChatCommand":
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


class GeneratedChatAnswer(ApiModel):
    answer: str = Field(min_length=1, max_length=20_000)
    # 답변에 실제로 인용한 자료의 [번호]만 담는다. 검색됐지만 쓰지 않은 자료는 출처로 노출하지 않는다.
    cited_indices: list[int] = Field(default_factory=list)


class ClassificationOutputExample(ApiModel):
    """안전성 분류 레이어의 예시 출력 계약."""

    label: Literal["SAFE", "REVIEW", "BLOCK"]
    category: str = Field(description="정책 위반 범주 또는 none")
    action: Literal["allow", "manual_review", "block"]
    reason: str = Field(description="근거를 요약한 짧은 설명")

    @model_validator(mode="after")
    def validate_label_action(self) -> "ClassificationOutputExample":
        expected_action = {
            "SAFE": "allow",
            "REVIEW": "manual_review",
            "BLOCK": "block",
        }[self.label]
        if self.action != expected_action:
            raise ValueError(f"{self.label} label requires {expected_action} action")
        return self


class ArchitectureComponent(ApiModel):
    name: str
    responsibility: str


class HarmonyRoleDescription(ApiModel):
    role: Literal["system", "developer", "user", "assistant", "tool"]
    purpose: str


class SafeguardPolicySection(ApiModel):
    name: Literal["Instruction", "Definitions", "Criteria", "Examples", "Output format"]
    purpose: str


class GeneratedArchitectureAnswer(ApiModel):
    """구조·아키텍처 질문에서 누락하면 안 되는 필수 섹션."""

    flow: str = Field(description="화살표로 표현한 전체 처리 흐름")
    components: list[ArchitectureComponent] = Field(
        min_length=1, description="구성요소와 각 책임"
    )
    harmony_roles: list[HarmonyRoleDescription] = Field(
        min_length=1,
        description="Harmony system, developer, user, assistant 역할과 channel 설명",
    )
    harmony_message_format: str = Field(
        description="Harmony 메시지 포맷. 일반 JSON과 구분"
    )
    safeguard_policy_sections: list[SafeguardPolicySection] = Field(
        min_length=1,
        description="Instruction, Definitions, Criteria, Examples, Output format 구조",
    )
    output_example: ClassificationOutputExample
    meetbowl_application: str = Field(description="Meetbowl 적용 위치와 권한 경계")
    cautions: list[str] = Field(min_length=1, description="운영·성능·보안 주의점")
    cited_indices: list[int] = Field(default_factory=list)
