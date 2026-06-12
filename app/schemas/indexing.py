from typing import Any, Literal
from uuid import UUID

from pydantic import Field

from app.schemas.base import ApiModel
from app.schemas.chat import ChatSourceType


# BE가 색인을 요청할 수 있는 문서 유형(백업 메일, 회의록, 개인 메모/드라이브, 공유 워크스페이스 파일).
DocumentType = Literal[
    "BACKUP_MAIL",
    "MEETING_MINUTES",
    "MINUTES",
    "PERSONAL_MEMO",
    "PERSONAL_DRIVE_FILE",
    "SHARED_WORKSPACE_FILE_VERSION",
]


class DocumentAccessScope(ApiModel):
    """문서를 조회할 수 있는 권한 범위(사용자/부서/공유 워크스페이스)."""

    user_ids: list[UUID] = Field(default_factory=list)
    department_ids: list[UUID] = Field(default_factory=list)
    shared_workspace_ids: list[UUID] = Field(default_factory=list)


class IndexDocumentRequest(ApiModel):
    """BE가 문서 색인을 요청할 때 보내는 요청 계약(외부 통신용 DTO)."""

    document_id: UUID
    document_type: DocumentType
    organization_id: UUID
    owner_user_id: UUID
    access_scope: DocumentAccessScope
    title: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1, max_length=100_000)
    metadata: dict[str, Any] = Field(default_factory=dict)


class IndexDocumentCommand(ApiModel):
    """translator를 거쳐 변환된 내부 색인 실행 계약(source_type으로 통일)."""

    document_id: UUID
    source_type: ChatSourceType
    organization_id: UUID
    owner_user_id: UUID
    shared_workspace_ids: list[UUID]
    title: str
    content: str
    metadata: dict[str, Any]


class IndexDocumentResult(ApiModel):
    """색인 처리 결과(문서 ID, 색인된 청크 수, 저장된 collection 이름)."""

    document_id: UUID
    indexed_chunks: int = Field(ge=1)
    collection: str


class IndexDocumentSuccessResponse(ApiModel):
    """BE로 돌려주는 색인 성공 응답 계약(외부 통신용 DTO)."""

    success: bool = True
    data: IndexDocumentResult
    message: str | None = None
