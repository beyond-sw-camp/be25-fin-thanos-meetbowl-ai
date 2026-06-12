"""Qdrant 하이브리드 검색 adapter가 권한 조건을 적용하고 결과를 출처로 변환하는지 검증한다."""

import asyncio
import json
from uuid import uuid4

import httpx

from app.rag.qdrant_chat import QdrantChatRetriever
from app.schemas.chat import ChatCommand


def test_qdrant_retriever_applies_be_access_context_and_maps_sources() -> None:
    workspace_id = uuid4()
    command = ChatCommand(
        request_id=uuid4(),
        correlation_id=uuid4(),
        user_id=uuid4(),
        organization_id=uuid4(),
        question="배포 일정",
        shared_workspace_ids=[workspace_id],
    )
    resource_id = uuid4()

    def handler(request: httpx.Request) -> httpx.Response:
        body = request.read().decode()
        assert str(command.organization_id) in body
        assert str(command.user_id) in body
        assert str(workspace_id) in body
        # dense/sparse 두 검색 경로를 RRF로 융합하는 하이브리드 질의여야 한다.
        parsed = json.loads(body)
        assert parsed["query"] == {"fusion": "rrf"}
        usings = {prefetch["using"] for prefetch in parsed["prefetch"]}
        assert usings == {"dense", "sparse"}
        return httpx.Response(
            200,
            json={
                "result": {
                    "points": [
                        {
                            "score": 0.91,
                            "payload": {
                                "sourceType": "MINUTES",
                                "sourceId": str(resource_id),
                                "title": "배포 회의록",
                                "content": "금요일 배포",
                            },
                        }
                    ]
                }
            },
        )

    async def run() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            retriever = QdrantChatRetriever(
                qdrant_url="http://qdrant",
                qdrant_collection="documents",
                http_client=client,
            )
            sources = await retriever.search(
                vector=[0.1, 0.2], query="배포 일정", command=command
            )

        assert sources[0].resource_id == resource_id
        assert sources[0].type == "MINUTES"
        assert sources[0].snippet == "금요일 배포"

    asyncio.run(run())
