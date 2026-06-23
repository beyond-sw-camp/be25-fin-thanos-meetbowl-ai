import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from pydantic_ai import Agent, RunContext
from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.usage import UsageLimits
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    UserPromptPart,
)

from app.core.errors import ProviderUnavailableError
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

# Gemini가 일시적 과부하/속도 제한일 때 돌려주는 상태 코드. 짧게 재시도하면 대개 회복된다.
_RETRYABLE_STATUS_CODES = frozenset({429, 503})
# 사용자의 '오늘/이번 주'는 한국 시간 기준이므로 모델에 KST 날짜를 알려준다.
_KST = timezone(timedelta(hours=9))


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
        max_retries: int = 2,
        retry_backoff_seconds: float = 0.5,
        document_max_chars: int = 16000,
        thinking_budget: int = 0,
    ) -> None:
        self._embedding_provider = embedding_provider
        self._retriever = retriever
        self._reranker = reranker
        self._model_name = model_name
        self._prompt_version = prompt_version
        self._candidate_pool = candidate_pool
        self._top_n = top_n
        self._max_retries = max_retries
        self._retry_backoff_seconds = retry_backoff_seconds
        self._document_max_chars = document_max_chars
        self._agent: Agent[ChatDeps, GeneratedChatAnswer] = Agent(
            model,
            deps_type=ChatDeps,
            output_type=GeneratedChatAnswer,
            system_prompt=CHAT_SYSTEM_PROMPT,
            # 사고(thinking) 예산을 0으로 두면 호출당 지연이 크게 준다(RAG Q&A엔 보통 불필요).
            model_settings={
                "temperature": temperature,
                "google_thinking_config": {"thinking_budget": thinking_budget},
                # Gemini 호출이 멈춰도 무한 대기하지 않도록 요청당 12초 상한을 둔다.
                "timeout": 12,
            },
        )

        @self._agent.system_prompt
        def _today() -> str:
            # '오늘/이번 주 만든 자료' 질의를 위해 현재 날짜(KST)를 모델에 알려준다.
            return f"오늘 날짜(KST 기준): {datetime.now(_KST).date().isoformat()}"

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
            return _format_with_citation_numbers(ctx.deps.retrieved_sources, sources)

        @self._agent.tool
        async def list_recent_documents(
            ctx: RunContext[ChatDeps],
            created_after: str | None = None,
            created_before: str | None = None,
            source_types: list[ChatSourceType] | None = None,
        ) -> str:
            """권한 범위 내 자료를 의미 검색 없이 최신순으로 나열한다.

            특정 주제가 아니라 '오늘 만든 메모 전체', '이번 주 메일', '6월 1일~10일 회의록'처럼
            날짜·유형 기준으로 모아 보여줘야 할 때 사용한다. created_after/created_before는
            ISO 날짜(예: 2026-06-17)로 생성 시점 범위를 지정하며, 끝 날짜는 그날 전체를 포함한다.
            특정 유형만 필요하면 source_types로 좁힌다.
            """
            documents = await ctx.deps.retriever.list_by_owner(
                command=ctx.deps.command,
                created_after=created_after,
                created_before=created_before,
                source_types=source_types,
            )
            _accumulate_sources(ctx.deps.retrieved_sources, documents)
            if not documents:
                return "조건에 맞는 자료가 없습니다."
            return _format_with_citation_numbers(ctx.deps.retrieved_sources, documents)

        @self._agent.tool
        async def count_documents(
            ctx: RunContext[ChatDeps],
            created_after: str | None = None,
            created_before: str | None = None,
            source_types: list[ChatSourceType] | None = None,
        ) -> str:
            """권한 범위 내 자료의 '개수'를 센다(청크가 아닌 문서 단위).

            '내 메모 몇 개야?', '이번 주 회의록 몇 건?'처럼 내용이 아니라 건수를 묻는 질문에 사용한다.
            created_after/created_before(ISO 날짜)로 기간을, source_types로 유형을 좁힐 수 있다.
            """
            count = await ctx.deps.retriever.count_by_owner(
                command=ctx.deps.command,
                created_after=created_after,
                created_before=created_before,
                source_types=source_types,
            )
            return f"조건에 맞는 자료는 총 {count}건입니다."

        @self._agent.tool
        async def get_document(ctx: RunContext[ChatDeps], citation_number: int) -> str:
            """특정 문서의 '전체 본문'을 가져온다(긴 문서 통째 요약·정밀 분석용).

            검색 일부 조각이 아니라 문서 전체가 필요할 때 사용한다. citation_number는 앞서
            search/list 결과로 제시된 [번호]이며, 그 자료의 본문 전체를 반환한다. 받은 본문을
            바탕으로 요약·분석해 답하라.
            """
            sources = ctx.deps.retrieved_sources
            if not 1 <= citation_number <= len(sources):
                return "그 번호에 해당하는 자료가 없습니다. 먼저 search/list로 자료를 찾으세요."
            source = sources[citation_number - 1]
            text = await ctx.deps.retriever.get_document(
                command=ctx.deps.command,
                resource_id=str(source.resource_id),
                max_chars=self._document_max_chars,
            )
            if not text:
                return "해당 문서의 본문을 찾지 못했습니다."
            return f"[{citation_number}] {source.title} 전체 본문:\n{text}"

    async def answer(self, command: ChatCommand) -> ChatResult:
        """질문과 직전 대화를 Agent에 전달하고 검증된 구조화 답변을 반환한다."""
        deps = ChatDeps(
            command=command,
            embedding_provider=self._embedding_provider,
            retriever=self._retriever,
        )
        result = await self._run_with_retry(deps, command)
        return ChatResult(
            answer=result.output.answer,
            sources=_select_cited_sources(
                deps.retrieved_sources, result.output.cited_indices
            ),
            model=self._model_name,
            prompt_version=self._prompt_version,
        )

    async def _run_with_retry(self, deps: ChatDeps, command: ChatCommand) -> Any:
        """Gemini가 일시적 과부하(429/503)면 짧은 백오프로 재시도하고, 끝내 실패하면 503으로 전달한다."""
        message_history = _to_model_messages(command.message_history) or None
        for attempt in range(self._max_retries + 1):
            try:
                return await self._agent.run(
                    command.question,
                    deps=deps,
                    message_history=message_history,
                    # 검색 tool 반복 폭주를 막아 응답이 무한정 길어지지 않게 모델 호출 횟수를 제한한다.
                    usage_limits=UsageLimits(request_limit=5),
                )
            except ModelHTTPError as error:
                # 과부하/속도 제한이 아니면 일시적 장애가 아니므로 재시도하지 않고 그대로 전달한다.
                if error.status_code not in _RETRYABLE_STATUS_CODES:
                    raise
                if attempt == self._max_retries:
                    # 재시도를 소진해도 과부하면 503을 그대로 전달한다.
                    raise ProviderUnavailableError(
                        "Gemini가 일시적으로 응답하지 못했습니다. 잠시 후 다시 시도해주세요."
                    ) from error
                # 재시도 누적 부하를 줄이기 위해 시도마다 대기 시간을 지수적으로 늘린다.
                await asyncio.sleep(self._retry_backoff_seconds * 2**attempt)
                # 검색 Tool이 이전 시도에서 채운 citation이 다음 시도에 중복 누적되지 않게 비운다.
                deps.retrieved_sources.clear()


def _to_model_messages(history: list[ChatMessage]) -> list[ModelMessage]:
    """내부 대화 이력을 PydanticAI 실행 문맥(ModelMessage)으로 변환한다."""
    messages: list[ModelMessage] = []
    for message in history:
        if message.role == "user":
            messages.append(ModelRequest(parts=[UserPromptPart(content=message.content)]))
        else:
            messages.append(ModelResponse(parts=[TextPart(content=message.content)]))
    return messages


def _format_with_citation_numbers(
    accumulated: list[ChatSource], shown: list[ChatSource]
) -> str:
    """제시할 자료를 누적 목록 기준의 안정적인 [번호]로 표기한다.

    모델은 이 번호로 인용을 표기하고, answer()가 같은 번호로 출처를 회수한다.
    여러 도구를 여러 번 호출해도 번호가 흔들리지 않는다.
    """
    index_by_id = {
        source.resource_id: number
        for number, source in enumerate(accumulated, start=1)
    }
    return "\n\n".join(
        f"[{index_by_id[source.resource_id]}] {source.title}\n{source.snippet}"
        for source in shown
    )


def _select_cited_sources(
    accumulated: list[ChatSource], cited_indices: list[int]
) -> list[ChatSource]:
    """모델이 답변에 실제로 인용한 [번호]만 출처로 회수한다(검색만 되고 안 쓴 자료는 제외).

    번호는 누적 목록 기준 1-based다. 범위를 벗어나거나 중복된 번호는 무시한다.
    """
    selected: list[ChatSource] = []
    seen: set[int] = set()
    for number in cited_indices:
        if 1 <= number <= len(accumulated) and number not in seen:
            seen.add(number)
            selected.append(accumulated[number - 1])
    return selected


def _accumulate_sources(
    accumulated: list[ChatSource], new_sources: list[ChatSource]
) -> None:
    """Tool이 여러 번 호출돼도 citation이 중복되지 않게 resource_id 기준으로 누적한다."""
    seen = {source.resource_id for source in accumulated}
    for source in new_sources:
        if source.resource_id not in seen:
            accumulated.append(source)
            seen.add(source.resource_id)
