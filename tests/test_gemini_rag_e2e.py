"""실제 Gemini 임베딩 + Qdrant로 색인·검색·권한 차단을 검증하는 E2E 테스트.

RUN_GEMINI_RAG_E2E=true이고 GEMINI_API_KEY가 있을 때만 실행된다.
"""

import asyncio
import os
from uuid import UUID

import httpx
import pytest

from app.container import build_container
from app.core.config import Settings
from app.schemas.chat import ChatCommand
from app.schemas.indexing import IndexDocumentRequest
from app.translators.indexing import index_request_to_command


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_GEMINI_RAG_E2E") != "true",
    reason="RUN_GEMINI_RAG_E2E=true일 때만 실제 Gemini/Qdrant 테스트를 실행합니다.",
)

INTERNAL_TOKEN = "meetbowl-local-internal-token-32bytes"
COLLECTION = "meetbowl-gemini-rag-e2e-test"
USER_ID = UUID("482f5551-ca99-4785-9446-810c851b3b06")
ORGANIZATION_ID = UUID("209daf7a-01e0-4acb-be86-33c224364b54")
WORKSPACE_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")


DOCUMENTS = [
    ("20000000-0000-4000-8000-000000000001", "BACKUP_MAIL", "오로라 백업 메일", "오로라 고객사 데모는 7월 3일 오후 2시이며 담당자는 김메일입니다.", USER_ID, [], {}),
    ("20000000-0000-4000-8000-000000000002", "PERSONAL_MEMO", "제피르 개인 메모", "제피르 발표 자료는 수요일 오전까지 완성하고 비용 표를 추가합니다.", USER_ID, [], {}),
    ("20000000-0000-4000-8000-000000000003", "PERSONAL_DRIVE_FILE", "솔라리스 개인 드라이브", "솔라리스 프로젝트 예산 상한은 4천만원이며 재무 검토일은 10월 5일입니다.", USER_ID, [], {}),
    ("20000000-0000-4000-8000-000000000004", "SHARED_WORKSPACE_FILE_VERSION", "네뷸라 공유 프로젝트", "네뷸라 프로젝트 운영 배포일은 8월 21일이며 승인 담당자는 박공유입니다.", UUID("99999999-9999-4999-8999-999999999999"), [WORKSPACE_ID], {"workspaceId": str(WORKSPACE_ID)}),
    ("20000000-0000-4000-8000-000000000005", "MEETING_MINUTES", "퀘이사 회의록", "퀘이사 회의에서 QA 종료일을 9월 12일로 결정했고 이회의가 후속 점검을 맡습니다.", USER_ID, [], {"meetingId": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"}),
]


def test_gemini_answers_from_all_authorized_sources() -> None:
    settings = Settings(
        llm_provider="gemini",
        internal_token=INTERNAL_TOKEN,
        qdrant_collection=COLLECTION,
    )
    assert settings.gemini_api_key
    async def run() -> None:
        container = build_container(settings)
        async with httpx.AsyncClient(timeout=5.0) as http_client:
            await http_client.delete(
                f"{settings.qdrant_url}/collections/{COLLECTION}"
            )
        for document_id, document_type, title, content, owner_id, workspaces, metadata in DOCUMENTS:
            request = IndexDocumentRequest.model_validate(
                {
                    "documentId": document_id,
                    "documentType": document_type,
                    "organizationId": str(ORGANIZATION_ID),
                    "ownerUserId": str(owner_id),
                    "accessScope": {"sharedWorkspaceIds": [str(value) for value in workspaces]},
                    "title": title,
                    "content": content,
                    "metadata": metadata,
                }
            )
            result = await container.document_indexing_workflow.execute(
                index_request_to_command(request)
            )
            assert result.indexed_chunks == 1

        allowed = await _chat(container.chat_workflow, [WORKSPACE_ID])
        assert {source.type for source in allowed.sources} == {
            "BACKUP_MAIL", "PERSONAL_MEMO", "PERSONAL_DRIVE_FILE",
            "SHARED_WORKSPACE_FILE_VERSION", "MINUTES",
        }
        for expected in ["7월 3일", "수요일", "4천만원", "8월 21일", "9월 12일"]:
            assert expected in allowed.answer

        denied = await _chat(container.chat_workflow, [])
        assert "SHARED_WORKSPACE_FILE_VERSION" not in {
            source.type for source in denied.sources
        }
        assert "8월 21일" not in denied.answer
        async with httpx.AsyncClient(timeout=5.0) as http_client:
            await http_client.delete(
                f"{settings.qdrant_url}/collections/{COLLECTION}"
            )

    asyncio.run(run())


async def _chat(chat_workflow, workspace_ids: list[UUID]):
    return await chat_workflow.execute(
        ChatCommand(
            request_id=UUID("11111111-1111-4111-8111-111111111111"),
            correlation_id=UUID("22222222-2222-4222-8222-222222222222"),
            user_id=USER_ID,
            organization_id=ORGANIZATION_ID,
            question="모든 자료에서 프로젝트별 일정, 담당자, 예산, 결정 사항을 빠짐없이 요약해줘.",
            shared_workspace_ids=workspace_ids,
        )
    )
