"""PydanticAI 챗봇 Agent가 검색 Tool 호출과 대화 문맥 전달을 수행하는지 검증한다.

- Agent가 접근 context로 검색 Tool을 호출하고 citation을 회수한다.
- messageHistory가 후속 질문의 답변 생성 문맥으로 Agent 실행에 전달된다.
"""

import asyncio
from uuid import uuid4

from pydantic_ai import capture_run_messages
from pydantic_ai.models.test import TestModel

from app.providers.fake_embedding import FakeEmbeddingProvider
from app.providers.fake_reranker import FakeReranker
from app.providers.pydantic_ai_chat import PydanticAiChatProvider, _to_model_messages
from app.schemas.chat import ChatCommand, ChatMessage, ChatSource


class _RecordingRetriever:
    """검색 Tool이 전달한 접근 context를 기록하는 stub retriever."""

    def __init__(self, sources: list[ChatSource]) -> None:
        self._sources = sources
        self.received_command: ChatCommand | None = None

    async def search(
        self,
        *,
        vector: list[float],
        query: str,
        command: ChatCommand,
        source_types: list[str] | None = None,
        limit: int = 10,
    ) -> list[ChatSource]:
        del vector, query, source_types, limit
        self.received_command = command
        return self._sources


def _provider(retriever: _RecordingRetriever) -> PydanticAiChatProvider:
    return PydanticAiChatProvider(
        model=TestModel(),
        embedding_provider=FakeEmbeddingProvider(),
        retriever=retriever,
        reranker=FakeReranker(),
        model_name="gemini-test",
        prompt_version="chat-v1",
    )


def _command(**overrides) -> ChatCommand:
    base = dict(
        request_id=uuid4(),
        correlation_id=uuid4(),
        user_id=uuid4(),
        organization_id=uuid4(),
        question="그 회의에서 정한 배포 날짜는?",
    )
    base.update(overrides)
    return ChatCommand(**base)


def test_to_model_messages_preserves_roles_and_content() -> None:
    history = [
        ChatMessage(role="user", content="배포 회의를 찾아줘"),
        ChatMessage(role="assistant", content="배포 회의록을 찾았습니다."),
    ]

    messages = _to_model_messages(history)

    assert messages[0].parts[0].content == "배포 회의를 찾아줘"
    assert messages[1].parts[0].content == "배포 회의록을 찾았습니다."


def test_agent_calls_search_tool_with_access_context_and_captures_sources() -> None:
    workspace_id = uuid4()
    source = ChatSource(
        type="MINUTES",
        resource_id=uuid4(),
        title="배포 회의록",
        snippet="금요일 배포로 결정",
        score=0.9,
    )
    retriever = _RecordingRetriever([source])
    command = _command(shared_workspace_ids=[workspace_id])

    result = asyncio.run(_provider(retriever).answer(command))

    # Agent가 검색 Tool을 호출하며 접근 context(command)를 그대로 전달했다.
    assert retriever.received_command is command
    assert retriever.received_command.shared_workspace_ids == [workspace_id]
    # Tool이 찾은 자료가 citation으로 회수되고, 구조화된 답변이 생성된다.
    assert result.sources == [source]
    assert result.answer
    assert result.model == "gemini-test"


def test_message_history_is_passed_into_agent_run() -> None:
    retriever = _RecordingRetriever([])
    command = _command(
        message_history=[
            ChatMessage(role="user", content="배포 회의를 찾아줘"),
            ChatMessage(role="assistant", content="배포 회의록을 찾았습니다."),
        ],
    )

    with capture_run_messages() as messages:
        asyncio.run(_provider(retriever).answer(command))

    contents = " ".join(
        str(getattr(part, "content", "")) for message in messages for part in message.parts
    )
    # 직전 대화가 Agent 실행 문맥에 포함되어 후속 질문의 근거로 쓰인다.
    assert "배포 회의를 찾아줘" in contents
    assert "배포 회의록을 찾았습니다." in contents


class _ReverseReranker:
    """검색 후보를 뒤집어 재정렬이 실제로 적용됐는지 검증하기 위한 stub reranker."""

    async def rerank(
        self, *, query: str, sources: list[ChatSource], top_n: int
    ) -> list[ChatSource]:
        del query
        return list(reversed(sources))[:top_n]


def test_provider_applies_reranker_between_retrieval_and_citation() -> None:
    first = ChatSource(
        type="MINUTES", resource_id=uuid4(), title="A", snippet="가", score=0.9
    )
    second = ChatSource(
        type="BACKUP_MAIL", resource_id=uuid4(), title="B", snippet="나", score=0.8
    )
    retriever = _RecordingRetriever([first, second])
    provider = PydanticAiChatProvider(
        model=TestModel(),
        embedding_provider=FakeEmbeddingProvider(),
        retriever=retriever,
        reranker=_ReverseReranker(),
        model_name="gemini-test",
        prompt_version="chat-v1",
    )

    result = asyncio.run(provider.answer(_command()))

    # reranker가 검색 결과와 citation 사이에서 순서를 바꿨다.
    assert [source.resource_id for source in result.sources] == [
        second.resource_id,
        first.resource_id,
    ]
