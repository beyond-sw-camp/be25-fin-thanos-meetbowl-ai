from uuid import uuid4

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app

client = TestClient(
    create_app(
        settings=Settings(
            minutes_summary_provider="fake",
            minutes_summary_model="fake-minutes-model",
        )
    )
)


def valid_request() -> dict:
    return {
        "meetingId": str(uuid4()),
        "organizationId": str(uuid4()),
        "hostUserId": str(uuid4()),
        "reviewerUserId": str(uuid4()),
        "title": "배포 회의",
        "startedAt": "2026-06-01T00:00:00Z",
        "endedAt": "2026-06-01T01:00:00Z",
        "participants": [
            {"userId": str(uuid4()), "name": "홍길동", "department": "기획팀"}
        ],
        "rawTranscript": "오늘 안건은 배포 일정입니다.\n금요일 배포를 결정했습니다.",
    }


def test_generate_minutes_returns_structured_draft() -> None:
    response = client.post("/api/v1/minutes/generate", json=valid_request())

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["status"] == "DRAFT"
    assert body["data"]["minutesDraft"]["decisions"] == ["금요일 배포를 결정했습니다."]
    assert body["data"]["editorContent"]["type"] == "doc"
    assert body["data"]["editorContent"]["content"][0]["type"] == "heading"
    assert body["data"]["model"] == "fake-minutes-model"


def test_generate_minutes_returns_common_validation_failure() -> None:
    payload = valid_request()
    payload.pop("meetingId")

    response = client.post("/api/v1/minutes/generate", json=payload)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_FAILED"


def test_generate_minutes_returns_context_not_found_for_empty_transcript() -> None:
    payload = valid_request()
    payload["rawTranscript"] = "  \n "

    response = client.post("/api/v1/minutes/generate", json=payload)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "AI_CONTEXT_NOT_FOUND"
