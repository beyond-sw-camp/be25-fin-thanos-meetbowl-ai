"""문서 색인 translator와 Qdrant 색인 workflow의 단위 테스트(외부 의존성 mock)."""

import asyncio
import json
from uuid import uuid4

import httpx

from app.providers.fake_embedding import FakeEmbeddingProvider
from app.rag.qdrant_index import QdrantDocumentIndexer
from app.schemas.indexing import IndexDocumentRequest
from app.translators.indexing import index_request_to_command
from app.workflows.document_indexing import DocumentIndexingWorkflow


def test_minutes_document_type_is_translated_to_chat_source_type() -> None:
    request = IndexDocumentRequest(
        document_id=uuid4(),
        document_type="MEETING_MINUTES",
        organization_id=uuid4(),
        owner_user_id=uuid4(),
        access_scope={"sharedWorkspaceIds": []},
        title="회의록",
        content="배포 결정",
    )

    command = index_request_to_command(request)

    assert command.source_type == "MINUTES"


def test_index_workflow_creates_collection_and_upserts_permission_metadata() -> None:
    requests: list[httpx.Request] = []
    workspace_id = uuid4()
    request = IndexDocumentRequest(
        document_id=uuid4(),
        document_type="SHARED_WORKSPACE_FILE_VERSION",
        organization_id=uuid4(),
        owner_user_id=uuid4(),
        access_scope={"sharedWorkspaceIds": [workspace_id]},
        title="프로젝트 계획",
        content="아틀라스 프로젝트는 금요일에 배포합니다.",
        metadata={"workspaceId": str(workspace_id)},
    )

    def handler(http_request: httpx.Request) -> httpx.Response:
        requests.append(http_request)
        if http_request.method == "GET":
            return httpx.Response(404)
        return httpx.Response(200, json={"status": "ok"})

    async def run() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            workflow = DocumentIndexingWorkflow(
                embedding_provider=FakeEmbeddingProvider(),
                indexer=QdrantDocumentIndexer(
                    qdrant_url="http://qdrant",
                    qdrant_collection="documents",
                    http_client=client,
                ),
            )
            result = await workflow.execute(index_request_to_command(request))
        assert result.indexed_chunks == 1

    asyncio.run(run())
    upsert_body = requests[-1].read().decode()
    assert str(workspace_id) in upsert_body
    assert "SHARED_WORKSPACE_FILE_VERSION" in upsert_body


def test_new_collection_creates_keyword_indexes_for_filter_fields() -> None:
    requests: list[httpx.Request] = []
    request = IndexDocumentRequest(
        document_id=uuid4(),
        document_type="MINUTES",
        organization_id=uuid4(),
        owner_user_id=uuid4(),
        access_scope={"sharedWorkspaceIds": []},
        title="회의록",
        content="배포 결정",
    )

    def handler(http_request: httpx.Request) -> httpx.Response:
        requests.append(http_request)
        if http_request.method == "GET":
            return httpx.Response(404)
        return httpx.Response(200, json={"status": "ok"})

    async def run() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            workflow = DocumentIndexingWorkflow(
                embedding_provider=FakeEmbeddingProvider(),
                indexer=QdrantDocumentIndexer(
                    qdrant_url="http://qdrant",
                    qdrant_collection="documents",
                    http_client=client,
                ),
            )
            await workflow.execute(index_request_to_command(request))

    asyncio.run(run())

    indexed_fields = {
        json.loads(http_request.read().decode())["field_name"]
        for http_request in requests
        if http_request.url.path.endswith("/index")
    }
    # 권한·유형 필터와 재색인 삭제에 쓰는 필드가 모두 인덱싱된다.
    assert indexed_fields == {
        "organizationId",
        "ownerUserId",
        "workspaceId",
        "sharedWorkspaceIds",
        "sourceType",
        "documentId",
    }


def test_long_document_is_indexed_as_multiple_chunk_points() -> None:
    requests: list[httpx.Request] = []
    document_id = uuid4()
    request = IndexDocumentRequest(
        document_id=document_id,
        document_type="MINUTES",
        organization_id=uuid4(),
        owner_user_id=uuid4(),
        access_scope={"sharedWorkspaceIds": []},
        title="긴 회의록",
        content="배포 일정과 예산을 논의했습니다. " * 60,  # 청크 한계를 넘는 본문
    )

    def handler(http_request: httpx.Request) -> httpx.Response:
        requests.append(http_request)
        if http_request.method == "GET":
            return httpx.Response(404)
        return httpx.Response(200, json={"status": "ok"})

    async def run() -> int:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            workflow = DocumentIndexingWorkflow(
                embedding_provider=FakeEmbeddingProvider(),
                indexer=QdrantDocumentIndexer(
                    qdrant_url="http://qdrant",
                    qdrant_collection="documents",
                    http_client=client,
                ),
                chunk_max_chars=200,
                chunk_overlap_chars=40,
            )
            result = await workflow.execute(index_request_to_command(request))
            return result.indexed_chunks

    indexed_chunks = asyncio.run(run())

    # 본문이 여러 청크로 나뉘어 색인된다.
    assert indexed_chunks > 1
    # 재색인 잔여 제거를 위해 documentId 기준 삭제가 upsert보다 먼저 호출된다.
    paths = [request.url.path for request in requests]
    assert any(path.endswith("/points/delete") for path in paths)
    # upsert 본문의 포인트 수가 청크 수와 일치한다.
    upsert_body = json.loads(requests[-1].read().decode())
    assert len(upsert_body["points"]) == indexed_chunks
    # 모든 청크 포인트는 같은 문서를 가리킨다(citation은 문서 단위).
    for point in upsert_body["points"]:
        assert point["payload"]["documentId"] == str(document_id)
