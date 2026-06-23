"""설계·아키텍처 질문에 필요한 답변 계약 검증."""

from app.prompts.chat import CHAT_SYSTEM_PROMPT, SINGLE_PASS_CHAT_PROMPT


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
