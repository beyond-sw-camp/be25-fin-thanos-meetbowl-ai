import secrets

from fastapi import APIRouter, Header, Request

from app.core.errors import AiError
from app.schemas.indexing import IndexDocumentRequest, IndexDocumentSuccessResponse
from app.translators.indexing import index_request_to_command

router = APIRouter(prefix="/indexes", tags=["indexes"])


@router.post("/documents", response_model=IndexDocumentSuccessResponse)
async def index_document(
    payload: IndexDocumentRequest,
    request: Request,
    internal_token: str | None = Header(default=None, alias="X-Internal-Token"),
) -> IndexDocumentSuccessResponse:
    """BE 내부 호출로 받은 문서를 RAG 검색용으로 색인한다(내부 토큰 인증 필요)."""
    # 내부 전용 API이므로 BE와 공유하는 내부 토큰을 timing-safe 방식으로 검증한다.
    expected_token = request.app.state.settings.internal_token
    if internal_token is None or not secrets.compare_digest(internal_token, expected_token):
        raise AiError("AI_RAG_ACCESS_DENIED", "내부 API 인증에 실패했습니다.", status_code=403)
    # 외부 계약(payload)을 내부 command로 변환한 뒤 색인 workflow에 위임한다.
    command = index_request_to_command(payload)
    result = await request.app.state.container.document_indexing_workflow.execute(command)
    return IndexDocumentSuccessResponse(data=result)
