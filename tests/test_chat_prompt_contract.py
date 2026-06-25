"""설계·아키텍처 질문에 필요한 답변 계약 검증."""

from app.prompts.chat import (
    CHAT_SYSTEM_PROMPT,
    COMMON_CHAT_POLICY,
    SINGLE_PASS_CHAT_PROMPT,
    STRICT_CHAT_CONSTRAINTS,
)


def test_architecture_answer_contract_is_present_in_both_prompts() -> None:
    for prompt in (CHAT_SYSTEM_PROMPT, SINGLE_PASS_CHAT_PROMPT):
        assert "전체 처리 흐름" in prompt
        assert "JSON" in prompt
        assert "Meetbowl" in prompt
        assert "Qdrant 접근 필터를 대체" in prompt


def test_single_pass_prompt_formats_without_treating_harmony_placeholders_as_fields() -> None:
    rendered = SINGLE_PASS_CHAT_PROMPT.format(
        today="2026-06-24", documents="[1] guide", question="q"
    )

    assert "{header}" in rendered
    assert "{content}" in rendered


def test_readability_and_multi_document_rules_are_present_in_both_prompts() -> None:
    for prompt in (CHAT_SYSTEM_PROMPT, SINGLE_PASS_CHAT_PROMPT):
        assert "3문장 이상이면 반드시 줄바꿈" in prompt
        assert "한 문단은 최대 3문장" in prompt
        assert "서로 다른 문서를 최소 2개 이상" in prompt


def test_rag_injection_and_followup_rules_are_shared_by_chat_prompts() -> None:
    for prompt in (CHAT_SYSTEM_PROMPT, SINGLE_PASS_CHAT_PROMPT):
        assert COMMON_CHAT_POLICY in prompt
        assert "분석 대상 데이터일 뿐" in prompt
        assert "직전 대화의 대상 문서" in prompt
        assert "핵심 식별자" in prompt


def test_few_shot_examples_cover_high_risk_cases() -> None:
    for prompt in (CHAT_SYSTEM_PROMPT, SINGLE_PASS_CHAT_PROMPT):
        assert "예시 1 - 참석자와 담당자 구분" in prompt
        assert "예시 2 - 다중 조건 주체 불일치" in prompt
        assert "예시 3 - 문서 내부 인젝션 무시" in prompt
        assert "예시 4 - Harmony 포맷과 분류 JSON 구분" in prompt
        assert "예시 5 - 제한 사항의 직접 관계 매핑" in prompt
        assert "예시 6 - 카테고리 직접 부합 항목만 선택" in prompt


def test_strict_constraints_are_shared_by_chat_prompts() -> None:
    for prompt in (CHAT_SYSTEM_PROMPT, SINGLE_PASS_CHAT_PROMPT):
        assert STRICT_CHAT_CONSTRAINTS in prompt
        assert "모든 질문에 빠짐없이 답하세요" in prompt
        assert "반드시 cited_indices에 포함" in prompt
        assert "추론으로 연결하지 마세요" in prompt
        assert "부정형·한정형 표현" in prompt
        assert "서비스 성격이 질문 카테고리에 직접 부합" in prompt
