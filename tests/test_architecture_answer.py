"""설계 질문도 최소 생성 스키마를 사용한다."""

from app.schemas.chat import GeneratedChatAnswer


def test_architecture_answer_uses_minimal_validated_schema() -> None:
    schema = GeneratedChatAnswer.model_json_schema(by_alias=True)

    assert set(schema["properties"]) == {"answer", "citedIndices"}
    assert schema["required"] == ["answer"]
