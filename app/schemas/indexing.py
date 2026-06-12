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

    def is_empty(self) -> bool:
        return (
            self.meeting_id is None
            and self.approved_at is None
            and self.workspace_id is None
            and self.file_version_id is None
            and self.mail_id is None
        )


class IndexDocumentRequest(ApiModel):
    document_id: UUID
    document_type: DocumentType
    organization_id: UUID
    owner_user_id: UUID
    title: str = Field(min_length=1)
    content: str = Field(min_length=1)
    metadata: DocumentMetadata = Field(default_factory=DocumentMetadata)
    access_scope: AccessScope


class IndexDocumentCommand(UtcDatetimeModel):
    document_id: UUID
    document_type: DocumentType
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
    document_type: DocumentType
    chunk_count: int = Field(ge=1)
    embedding_model: str
    indexed_at: datetime


class IndexDocumentSuccessResponse(ApiModel):
    success: bool = True
    data: DocumentIndexingResult
    message: str | None = None
