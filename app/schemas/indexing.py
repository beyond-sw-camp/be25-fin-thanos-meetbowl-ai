from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from app.schemas.base import ApiModel, UtcDatetimeModel


DocumentType = Literal[
    "BACKUP_MAIL",
    "MEETING_MINUTES",
    "MINUTES",
    "PERSONAL_MEMO",
    "PERSONAL_DRIVE_FILE",
    "SHARED_WORKSPACE_FILE_VERSION",
]


class AccessScope(UtcDatetimeModel):
    user_ids: list[UUID] = Field(default_factory=list)
    department_ids: list[UUID] = Field(default_factory=list)
    shared_workspace_ids: list[UUID] = Field(default_factory=list)

    def is_empty(self) -> bool:
        return (
            not self.user_ids
            and not self.department_ids
            and not self.shared_workspace_ids
        )


class DocumentMetadata(UtcDatetimeModel):
    meeting_id: UUID | None = None
    approved_at: datetime | None = None
    workspace_id: UUID | None = None
    file_version_id: UUID | None = None
    mail_id: UUID | None = None
    # 파일 문서(드라이브/공유)는 본문 대신 S3 위치/타입을 metadata에 담는다(BE가 여기로 보냄).
    storage_key: str | None = None
    content_type: str | None = None

    def is_empty(self) -> bool:
        return (
            self.meeting_id is None
            and self.approved_at is None
            and self.workspace_id is None
            and self.file_version_id is None
            and self.mail_id is None
            and self.storage_key is None
            and self.content_type is None
        )


class IndexDocumentRequest(ApiModel):
    document_id: UUID
    document_type: DocumentType
    # 개인 자료(메모/메일/개인워크)는 조직 미소속 사용자도 색인 대상이므로 organization은 선택값이다.
    organization_id: UUID | None = None
    owner_user_id: UUID
    title: str = Field(min_length=1)
    # 텍스트 자료는 content를, 파일 자료는 metadata.storage_key를 보낸다(둘 중 하나는 있어야 함).
    content: str | None = None
    metadata: DocumentMetadata = Field(default_factory=DocumentMetadata)
    access_scope: AccessScope


class IndexDocumentCommand(UtcDatetimeModel):
    document_id: UUID
    document_type: DocumentType
    organization_id: UUID | None = None
    owner_user_id: UUID
    title: str = Field(min_length=1)
    # 텍스트 자료는 content를, 파일 자료는 metadata.storage_key+content_type을 채워 S3에서 추출한다.
    content: str | None = None
    access_scope: AccessScope
    metadata: DocumentMetadata = Field(default_factory=DocumentMetadata)
    created_at: datetime


class DocumentChunk(UtcDatetimeModel):
    chunk_index: int = Field(ge=0)
    content: str = Field(min_length=1)
    embedding_text: str = Field(min_length=1)


class DocumentIndexingResult(UtcDatetimeModel):
    document_id: UUID
    document_type: DocumentType
    chunk_count: int = Field(ge=1)
    embedding_model: str
    indexed_at: datetime


class IndexDocumentSuccessResponse(ApiModel):
    success: bool = True
    data: DocumentIndexingResult
    message: str | None = None
