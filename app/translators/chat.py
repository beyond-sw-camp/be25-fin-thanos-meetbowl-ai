from app.schemas.chat import ChatCommand, ChatMessage, ChatResult
from app.schemas.chat_api import (
    BeChatDataResponse,
    BeChatRequest,
    BeChatSourceResponse,
    BeChatSuccessResponse,
)


def be_request_to_chat_command(request: BeChatRequest) -> ChatCommand:
    """BE REST 계약을 provider와 분리된 챗봇 실행 계약으로 변환한다."""
    return ChatCommand(
        request_id=request.request_id,
        correlation_id=request.correlation_id,
        user_id=request.user_id,
        organization_id=request.organization_id,
        question=request.question,
        message_history=[
            ChatMessage(role=message.role, content=message.content)
            for message in request.message_history
        ],
        shared_workspace_ids=list(request.shared_workspace_ids),
    )


def chat_result_to_be_response(result: ChatResult) -> BeChatSuccessResponse:
    """내부 결과를 현재 BE가 소비하는 성공 응답 계약으로 변환한다."""
    return BeChatSuccessResponse(
        data=BeChatDataResponse(
            answer=result.answer,
            sources=[
                BeChatSourceResponse(
                    type=source.type,
                    resource_id=source.resource_id,
                    title=source.title,
                    snippet=source.snippet,
                    score=source.score,
                )
                for source in result.sources
            ],
            model=result.model,
            prompt_version=result.prompt_version,
        )
    )
