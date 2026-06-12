from uuid import uuid4

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


INTERNAL_TOKEN = "meetbowl-local-internal-token-32bytes"
client = TestClient(
    create_app(settings=Settings(llm_provider="fake", internal_token=INTERNAL_TOKEN))
)


def valid_request() -> dict:
    return {
        "requestId": str(uuid4()),
        "correlationId": str(uuid4()),
        "userId": str(uuid4()),
        "organizationId": str(uuid4()),
        "question": "지난 회의의 배포 일정을 알려줘",
        "messageHistory": [],
        "sharedWorkspaceIds": [str(uuid4())],
    }


def test_chat_returns_stateless_structured_response() -> None:
    response = client.post(
        "/api/v1/chat",
        json=valid_request(),
        headers={"X-Internal-Token": INTERNAL_TOKEN},
    )

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "data": {
            "answer": "검색 가능한 자료에서 질문의 근거를 확인하지 못했습니다.",
            "sources": [],
            "model": "fake-chat-model",
            "promptVersion": "chat-v1",
        },
        "message": None,
    }


def test_chat_rejects_missing_internal_token() -> None:
    response = client.post("/api/v1/chat", json=valid_request())

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "AI_RAG_ACCESS_DENIED"


def test_chat_rejects_non_alternating_history() -> None:
    payload = valid_request()
    payload["messageHistory"] = [
        {"role": "user", "content": "첫 질문"},
        {"role": "user", "content": "연속 질문"},
    ]

    response = client.post(
        "/api/v1/chat",
        json=payload,
        headers={"X-Internal-Token": INTERNAL_TOKEN},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_FAILED"
