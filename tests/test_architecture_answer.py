"""설계 질문의 필수 섹션 렌더링 검증."""

from app.providers.single_pass_chat import _format_architecture_answer
from app.schemas.chat import (
    ArchitectureComponent,
    ClassificationOutputExample,
    GeneratedArchitectureAnswer,
    HarmonyRoleDescription,
    SafeguardPolicySection,
)


def test_formats_all_required_architecture_sections() -> None:
    output = GeneratedArchitectureAnswer(
        flow="입력 → 분류 → 조치",
        components=[ArchitectureComponent(name="분류기", responsibility="정책 판정")],
        harmony_roles=[
            HarmonyRoleDescription(role="system", purpose="메타 정보"),
            HarmonyRoleDescription(role="developer", purpose="정책"),
        ],
        harmony_message_format="<|start|>{header}<|message|>{content}<|end|>",
        safeguard_policy_sections=[
            SafeguardPolicySection(name="Instruction", purpose="분류 지시"),
            SafeguardPolicySection(name="Definitions", purpose="용어 정의"),
            SafeguardPolicySection(name="Criteria", purpose="판정 기준"),
            SafeguardPolicySection(name="Examples", purpose="경계 사례"),
        ],
        output_example=ClassificationOutputExample(
            label="REVIEW",
            category="workspace_permission",
            action="manual_review",
            reason="권한 범위가 불명확함",
        ),
        meetbowl_application="권한 검사는 BE에서 유지",
        cautions=["분류 모델으로 인증을 대체하지 않음"],
        cited_indices=[1, 2],
    )

    answer = _format_architecture_answer(output)

    for heading in (
        "전체 처리 흐름",
        "구성요소별 책임",
        "Harmony 메시지 구조",
        "Safeguard 정책 구조",
        "분류 결과 JSON 예시",
        "Meetbowl 적용",
        "주의점",
    ):
        assert heading in answer
    assert '"label": "REVIEW"' in answer
