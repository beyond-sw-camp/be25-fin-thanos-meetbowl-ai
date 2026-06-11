import secrets

from fastapi import APIRouter, Header, Request

from app.core.errors import AiError
from app.schemas.chat import ChatRequest, ChatSuccessResponse

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatSuccessResponse)
async def chat(
    payload: ChatRequest,
    request: Request,
    internal_token: str | None = Header(default=None, alias="X-Internal-Token"),
) -> ChatSuccessResponse:
    expected_token = request.app.state.settings.internal_token
    if internal_token is None or not secrets.compare_digest(internal_token, expected_token):
        raise AiError("AI_RAG_ACCESS_DENIED", "내부 API 인증에 실패했습니다.", status_code=403)
    result = await request.app.state.container.chat_workflow.execute(payload)
    return ChatSuccessResponse(data=result)
