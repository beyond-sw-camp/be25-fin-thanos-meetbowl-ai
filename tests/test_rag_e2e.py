"""Fake 임베딩 + 실제 Qdrant로 색인·검색·권한 차단을 검증하는 E2E 테스트.

RUN_RAG_E2E=true일 때만 실행되며 Gemini 키 없이 RAG 흐름을 확인한다.
"""

import os
from uuid import UUID

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_RAG_E2E") != "true",
    reason="RUN_RAG_E2E=true일 때만 실제 Qdrant 통합 테스트를 실행합니다.",
)

INTERNAL_TOKEN = "meetbowl-local-internal-token-32bytes"
COLLECTION = "meetbowl-rag-e2e-test"
USER_ID = UUID("482f5551-ca99-4785-9446-810c851b3b06")
ORGANIZATION_ID = UUID("209daf7a-01e0-4acb-be86-33c224364b54")
WORKSPACE_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")


DOCUMENTS = [
    (
        "10000000-0000-4000-8000-000000000001",
        "BACKUP_MAIL",
        "백업 메일 - 오로라 일정",
        "오로라 고객사 데모는 7월 3일 오후 2시이며 담당자는 김메일입니다.",
        USER_ID,
        [],
        {},
    ),
    (
        "10000000-0000-4000-8000-000000000002",
        "PERSONAL_MEMO",
        "개인 메모 - 제피르 준비",
        "제피르 발표 자료는 수요일 오전까지 완성하고 비용 표를 추가합니다.",
        USER_ID,
        [],
        {},
    ),
    (
        "10000000-0000-4000-8000-000000000003",
        "PERSONAL_DRIVE_FILE",
        "개인 드라이브 - 솔라리스 예산",
        "솔라리스 프로젝트 예산 상한은 4천만원이며 재무 검토일은 10월 5일입니다.",
        USER_ID,
        [],
        {},
    ),
    (
        "10000000-0000-4000-8000-000000000004",
        "SHARED_WORKSPACE_FILE_VERSION",
        "공유 프로젝트 - 네뷸라 배포",
        "네뷸라 프로젝트 운영 배포일은 8월 21일이며 승인 담당자는 박공유입니다.",
        UUID("99999999-9999-4999-8999-999999999999"),
        [WORKSPACE_ID],
        {"workspaceId": str(WORKSPACE_ID)},
    ),
    (
        "10000000-0000-4000-8000-000000000005",
        "MEETING_MINUTES",
        "퀘이사 회의록",
        "퀘이사 회의에서 QA 종료일을 9월 12일로 결정했고 이회의가 후속 점검을 맡습니다.",
        USER_ID,
        [],
        {"meetingId": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"},
    ),
]


def test_real_qdrant_indexes_all_chat_sources_and_enforces_workspace_access() -> None:
    qdrant_url = "http://127.0.0.1:6333"
    httpx.delete(f"{qdrant_url}/collections/{COLLECTION}", timeout=5.0)
    client = TestClient(
        create_app(
            settings=Settings(
                llm_provider="fake",
                fake_chat_rag_enabled=True,
                internal_token=INTERNAL_TOKEN,
                qdrant_url=qdrant_url,
                qdrant_collection=COLLECTION,
            )
        )
    )
    headers = {"X-Internal-Token": INTERNAL_TOKEN}
    try:
        for document_id, document_type, title, content, owner_id, workspaces, metadata in DOCUMENTS:
            response = client.post(
                "/api/v1/indexes/documents",
                headers=headers,
                json={
                    "documentId": document_id,
                    "documentType": document_type,
                    "organizationId": str(ORGANIZATION_ID),
                    "ownerUserId": str(owner_id),
                    "accessScope": {"sharedWorkspaceIds": [str(value) for value in workspaces]},
                    "title": title,
                    "content": content,
                    "metadata": metadata,
                },
            )
            assert response.status_code == 200, response.text

        allowed = _chat(client, headers, [WORKSPACE_ID])
        allowed_types = {source["type"] for source in allowed["sources"]}
        assert allowed_types == {
            "BACKUP_MAIL",
            "PERSONAL_MEMO",
            "PERSONAL_DRIVE_FILE",
            "SHARED_WORKSPACE_FILE_VERSION",
            "MINUTES",
        }
        assert "네뷸라 프로젝트 운영 배포일은 8월 21일" in allowed["answer"]

        denied = _chat(client, headers, [])
        denied_types = {source["type"] for source in denied["sources"]}
        assert "SHARED_WORKSPACE_FILE_VERSION" not in denied_types
        assert denied_types == {
            "BACKUP_MAIL",
            "PERSONAL_MEMO",
            "PERSONAL_DRIVE_FILE",
            "MINUTES",
        }
    finally:
        httpx.delete(f"{qdrant_url}/collections/{COLLECTION}", timeout=5.0)


def _chat(
    client: TestClient, headers: dict[str, str], workspace_ids: list[UUID]
) -> dict:
    response = client.post(
        "/api/v1/chat",
        headers=headers,
        json={
            "requestId": "11111111-1111-4111-8111-111111111111",
            "correlationId": "22222222-2222-4222-8222-222222222222",
            "userId": str(USER_ID),
            "organizationId": str(ORGANIZATION_ID),
            "question": "업무 자료의 일정, 담당자, 결정 사항을 정리해줘",
            "messageHistory": [],
            "sharedWorkspaceIds": [str(value) for value in workspace_ids],
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]
