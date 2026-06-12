"""회의록과 챗봇 기능이 같은 앱에서 독립적으로 공존하는지 검증하는 회귀 테스트."""

from uuid import uuid4

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


INTERNAL_TOKEN = "meetbowl-local-internal-token-32bytes"


def test_minutes_and_chat_use_separate_models_in_same_application() -> None:
    client = TestClient(
        create_app(
            settings=Settings(
                llm_provider="fake",
                fake_model_name="fake-minutes-model",
                fake_chat_model_name="fake-chat-model",
                internal_token=INTERNAL_TOKEN,
            )
        )
    )
    minutes_response = client.post(
        "/api/v1/minutes/generate",
        json={
            "meetingId": str(uuid4()),
            "organizationId": str(uuid4()),
            "hostUserId": str(uuid4()),
            "reviewerUserId": str(uuid4()),
            "title": "배포 회의",
            "startedAt": "2026-06-01T00:00:00Z",
            "endedAt": "2026-06-01T01:00:00Z",
            "participants": [],
            "rawTranscript": "금요일 배포를 결정했습니다.",
        },
    )
    chat_response = client.post(
        "/api/v1/chat",
        headers={"X-Internal-Token": INTERNAL_TOKEN},
        json={
            "requestId": str(uuid4()),
            "correlationId": str(uuid4()),
            "userId": str(uuid4()),
            "organizationId": str(uuid4()),
            "question": "지난 회의의 배포 일정을 알려줘",
            "messageHistory": [],
            "sharedWorkspaceIds": [],
        },
    )

    assert minutes_response.status_code == 200
    assert minutes_response.json()["data"]["model"] == "fake-minutes-model"
    assert chat_response.status_code == 200
    assert chat_response.json()["data"]["model"] == "fake-chat-model"
