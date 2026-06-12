from dataclasses import dataclass, field
from typing import Any

from pydantic_ai import Agent, RunContext
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    UserPromptPart,
)

from app.ports.embedding_provider import EmbeddingProvider
from app.ports.reranker import Reranker
from app.prompts.chat import CHAT_SYSTEM_PROMPT
from app.rag.qdrant_chat import QdrantChatRetriever
from app.schemas.chat import (
    ChatCommand,
    ChatMessage,
    ChatResult,
    ChatSource,
    ChatSourceType,
    GeneratedChatAnswer,
)


@dataclass
class ChatDeps:
    """Agent 실행마다 주입되는 접근 context와 검색 의존성.

    `retrieved_sources`는 검색 Tool이 채운 citation을 답변 생성 후 회수하기 위한 통로다.
    """

    command: ChatCommand
    embedding_provider: EmbeddingProvider
    retriever: QdrantChatRetriever
    retrieved_sources: list[ChatSource] = field(default_factory=list)


class PydanticAiChatProvider:
    """PydanticAI Agent가 권한 필터 검색 Tool을 호출해 답하는 챗봇 provider.

    접근 context를 Agent dependency로 주입하고, Agent가 호출하는 검색 Tool은
    공통 권한 filter builder(`QdrantChatRetriever`)만 사용해 열람 범위를 제한한다.
    """

    def __init__(
        self,
        *,
        model: Any,
        embedding_provider: EmbeddingProvider,
        retriever: QdrantChatRetriever,
        reranker: Reranker,
        model_name: str,
        prompt_version: str,
        temperature: float = 0.2,
        candidate_pool: int = 30,
        top_n: int = 10,
    ) -> None:
        self._embedding_provider = embedding_provider
        self._retriever = retriever
        self._reranker = reranker
        self._model_name = model_name
        self._prompt_version = prompt_version
        self._candidate_pool = candidate_pool
        self._top_n = top_n
        self._agent: Agent[ChatDeps, GeneratedChatAnswer] = Agent(
            model,
            deps_type=ChatDeps,
            output_type=GeneratedChatAnswer,
            system_prompt=CHAT_SYSTEM_PROMPT,
            model_settings={"temperature": temperature},
        )

        @self._agent.tool
        async def search_documents(
            ctx: RunContext[ChatDeps],
            query: str,
            source_types: list[ChatSourceType] | None = None,
        ) -> str:
            """권한 범위 내 업무 자료를 검색해 답변 근거로 제공한다.

            질문이 특정 자료 유형(메일/회의록/개인메모 등)에 한정될 때만 source_types로
            범위를 좁히고, 그렇지 않으면 비워 전체 유형을 검색한다.
            """
            vector = await ctx.deps.embedding_provider.embed(query)
            # 넓게(pool) 검색해 후보를 모은 뒤 reranker로 정밀하게 상위 top_n을 추린다.
            candidates = await ctx.deps.retriever.search(
                vector=vector,
                query=query,
                command=ctx.deps.command,
                source_types=source_types,
                limit=self._candidate_pool,
            )
            sources = await self._reranker.rerank(
                query=query, sources=candidates, top_n=self._top_n
            )
            _accumulate_sources(ctx.deps.retrieved_sources, sources)
            if not sources:
                return "검색 가능한 자료에서 근거를 찾지 못했습니다."
            return "\n\n".join(
                f"[{index}] {source.title}\n{source.snippet}"
                for index, source in enumerate(sources, start=1)
            )

    async def answer(self, command: ChatCommand) -> ChatResult:
        """질문과 직전 대화를 Agent에 전달하고 검증된 구조화 답변을 반환한다."""
        deps = ChatDeps(
            command=command,
            embedding_provider=self._embedding_provider,
            retriever=self._retriever,
        )
        result = await self._agent.run(
            command.question,
            deps=deps,
            message_history=_to_model_messages(command.message_history) or None,
        )
        return ChatResult(
            answer=result.output.answer,
            sources=deps.retrieved_sources,
            model=self._model_name,
            prompt_version=self._prompt_version,
        )


def _to_model_messages(history: list[ChatMessage]) -> list[ModelMessage]:
    """내부 대화 이력을 PydanticAI 실행 문맥(ModelMessage)으로 변환한다."""
    messages: list[ModelMessage] = []
    for message in history:
        if message.role == "user":
            messages.append(ModelRequest(parts=[UserPromptPart(content=message.content)]))
        else:
            messages.append(ModelResponse(parts=[TextPart(content=message.content)]))
    return messages


def _accumulate_sources(
    accumulated: list[ChatSource], new_sources: list[ChatSource]
) -> None:
    """Tool이 여러 번 호출돼도 citation이 중복되지 않게 resource_id 기준으로 누적한다."""
    seen = {source.resource_id for source in accumulated}
    for source in new_sources:
        if source.resource_id not in seen:
            accumulated.append(source)
            seen.add(source.resource_id)
