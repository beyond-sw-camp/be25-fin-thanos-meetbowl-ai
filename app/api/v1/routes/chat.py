import secrets

from fastapi import APIRouter, Header, Request

from app.core.errors import AiError
from app.schemas.chat_api import BeChatRequest, BeChatSuccessResponse
from app.translators.chat import be_request_to_chat_command, chat_result_to_be_response

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=BeChatSuccessResponse)
async def chat(
    payload: BeChatRequest,
    request: Request,
    internal_token: str | None = Header(default=None, alias="X-Internal-Token"),
) -> BeChatSuccessResponse:
    expected_token = request.app.state.settings.internal_token
    if internal_token is None or not secrets.compare_digest(internal_token, expected_token):
        raise AiError("AI_RAG_ACCESS_DENIED", "내부 API 인증에 실패했습니다.", status_code=403)
    command = be_request_to_chat_command(payload)
    result = await request.app.state.container.chat_workflow.execute(command)
    return chat_result_to_be_response(result)
