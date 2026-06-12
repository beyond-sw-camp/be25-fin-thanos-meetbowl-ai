from app.schemas.indexing import IndexDocumentCommand, IndexDocumentRequest


# BE 색인 문서 유형을 챗봇 출처 유형으로 매핑한다.
# (BE의 MEETING_MINUTES는 챗봇 출처에서는 MINUTES로 통일한다.)
SOURCE_TYPE_BY_DOCUMENT_TYPE = {
    "BACKUP_MAIL": "BACKUP_MAIL",
    "MEETING_MINUTES": "MINUTES",
    "MINUTES": "MINUTES",
    "PERSONAL_MEMO": "PERSONAL_MEMO",
    "PERSONAL_DRIVE_FILE": "PERSONAL_DRIVE_FILE",
    "SHARED_WORKSPACE_FILE_VERSION": "SHARED_WORKSPACE_FILE_VERSION",
}


def index_request_to_command(request: IndexDocumentRequest) -> IndexDocumentCommand:
    """BE 색인 요청 계약을 내부 색인 실행 계약(IndexDocumentCommand)으로 변환한다."""
    return IndexDocumentCommand(
        document_id=request.document_id,
        source_type=SOURCE_TYPE_BY_DOCUMENT_TYPE[request.document_type],
        organization_id=request.organization_id,
        owner_user_id=request.owner_user_id,
        shared_workspace_ids=list(request.access_scope.shared_workspace_ids),
        title=request.title,
        content=request.content,
        metadata=dict(request.metadata),
    )
