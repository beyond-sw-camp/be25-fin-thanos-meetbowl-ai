from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import Field

from app.schemas.base import UtcDatetimeModel


class AccessScope(UtcDatetimeModel):
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

    def is_empty(self) -> bool:
        return (
            self.meeting_id is None
            and self.approved_at is None
            and self.workspace_id is None
            and self.file_version_id is None
            and self.mail_id is None
        )


class IndexDocumentCommand(UtcDatetimeModel):
    document_id: UUID
    document_type: str = Field(min_length=1)
    organization_id: UUID
    owner_user_id: UUID
    title: str = Field(min_length=1)
    content: str = Field(min_length=1)
    access_scope: AccessScope
    metadata: DocumentMetadata = Field(default_factory=DocumentMetadata)
    created_at: datetime


class DocumentChunk(UtcDatetimeModel):
    chunk_index: int = Field(ge=0)
    content: str = Field(min_length=1)
    embedding_text: str = Field(min_length=1)


class DocumentIndexingResult(UtcDatetimeModel):
    document_id: UUID
    document_type: str
    chunk_count: int = Field(ge=1)
    embedding_model: str
    indexed_at: datetime
