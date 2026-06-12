"""챗봇 대화가 비영속으로 처리되는지 검증한다.

- Qdrant에는 검색(query)만 수행하고 대화 내용을 기록(upsert)하지 않는다.
- 질문/답변 본문이 로그에 남지 않는다.
"""

import asyncio
import logging
from uuid import uuid4

import httpx
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.providers.fake_chat import FakeChatProvider
from app.providers.fake_embedding import FakeEmbeddingProvider
from app.rag.qdrant_chat import QdrantChatRetriever
from app.schemas.chat import ChatCommand


INTERNAL_TOKEN = "meetbowl-local-internal-token-32bytes"


def test_chat_only_queries_qdrant_and_never_writes_conversation() -> None:
    requests: list[httpx.Request] = []
    question = "이번 분기 배포 일정 알려줘"

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"result": {"points": []}})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = FakeChatProvider(
                "fake-chat-model",
                "chat-v1",
                embedding_provider=FakeEmbeddingProvider(),
                retriever=QdrantChatRetriever(
                    qdrant_url="http://qdrant",
                    qdrant_collection="documents",
                    http_client=client,
                ),
            )
            return await provider.answer(
                ChatCommand(
                    request_id=uuid4(),
                    correlation_id=uuid4(),
                    user_id=uuid4(),
                    organization_id=uuid4(),
                    question=question,
                )
            )

    result = asyncio.run(run())

    # Qdrant 호출은 검색(query)만 발생해야 하고, 쓰기(upsert) 경로는 호출되지 않아야 한다.
    assert requests, "챗봇은 Qdrant 검색을 한 번 이상 수행해야 한다"
    for request in requests:
        assert request.method == "POST"
        assert request.url.path.endswith("/points/query")
    # 질문 본문은 Qdrant로 전송되지 않아야 한다(벡터와 권한 필터만 전송).
    for request in requests:
        assert question not in request.read().decode()
    assert result.answer


def test_chat_api_does_not_log_question_or_answer(caplog) -> None:
    client = TestClient(
        create_app(settings=Settings(llm_provider="fake", internal_token=INTERNAL_TOKEN))
    )
    question = "민감한 배포 일정을 자세히 알려줘"

    with caplog.at_level(logging.DEBUG):
        response = client.post(
            "/api/v1/chat",
            headers={"X-Internal-Token": INTERNAL_TOKEN},
            json={
                "requestId": str(uuid4()),
                "correlationId": str(uuid4()),
                "userId": str(uuid4()),
                "organizationId": str(uuid4()),
                "question": question,
                "messageHistory": [],
                "sharedWorkspaceIds": [],
            },
        )

    assert response.status_code == 200
    answer = response.json()["data"]["answer"]

    # 어떤 로그 레코드에도 질문/답변 본문이 남지 않아야 한다.
    logged = "\n".join(record.getMessage() for record in caplog.records)
    assert question not in logged
    assert answer not in logged
