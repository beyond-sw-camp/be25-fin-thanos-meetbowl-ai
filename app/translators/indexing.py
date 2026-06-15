from datetime import datetime, timezone

from app.schemas.indexing import IndexDocumentCommand, IndexDocumentRequest


def index_request_to_command(request: IndexDocumentRequest) -> IndexDocumentCommand:
    """BE 색인 요청 계약을 내부 색인 실행 계약(IndexDocumentCommand)으로 변환한다."""
    return IndexDocumentCommand(
        document_id=request.document_id,
        document_type=request.document_type,
        organization_id=request.organization_id,
        owner_user_id=request.owner_user_id,
        title=request.title,
        content=request.content,
        access_scope=request.access_scope,
        metadata=request.metadata,
        created_at=datetime.now(timezone.utc),
    )
