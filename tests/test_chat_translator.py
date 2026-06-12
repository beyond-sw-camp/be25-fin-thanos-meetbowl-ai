"""BE 챗봇 요청·응답 계약과 내부 모델 간 translator 변환 단위 테스트."""

from uuid import uuid4

from app.schemas.chat import ChatResult, ChatSource
from app.schemas.chat_api import BeChatRequest
from app.translators.chat import be_request_to_chat_command, chat_result_to_be_response


def test_be_request_is_translated_to_internal_chat_command() -> None:
    request = BeChatRequest.model_validate(
        {
            "requestId": str(uuid4()),
            "correlationId": str(uuid4()),
            "userId": str(uuid4()),
            "organizationId": str(uuid4()),
            "question": "앞선 답변의 근거를 알려줘",
            "messageHistory": [
                {"role": "user", "content": "배포 일정을 알려줘"},
                {"role": "assistant", "content": "금요일 배포로 확인됩니다."},
            ],
            "sharedWorkspaceIds": [str(uuid4())],
        }
    )

    command = be_request_to_chat_command(request)

    assert command.question == request.question
    assert command.message_history[0].content == "배포 일정을 알려줘"
    assert command.message_history is not request.message_history
    assert command.shared_workspace_ids == request.shared_workspace_ids


def test_internal_chat_result_is_translated_to_be_contract() -> None:
    source_id = uuid4()
    result = ChatResult(
        answer="회의록에서 금요일 배포로 확인됩니다.",
        sources=[
            ChatSource(
                type="MINUTES",
                resource_id=source_id,
                title="배포 회의록",
                snippet="금요일 배포",
                score=0.92,
            )
        ],
        model="fake-chat-model",
        prompt_version="chat-v1",
    )

    response = chat_result_to_be_response(result)
    body = response.model_dump(by_alias=True, mode="json")

    assert body["data"]["sources"][0]["resourceId"] == str(source_id)
    assert body["data"]["promptVersion"] == "chat-v1"
