import logging
import time
from datetime import datetime

from app.ports.embedding_provider import EmbeddingProvider
from app.ports.generation import (
    StructuredGenerationPort,
    StructuredGenerationRequest,
)
from app.ports.reranker import Reranker
from app.prompts.chat import SINGLE_PASS_CHAT_PROMPT
from app.providers.pydantic_ai_chat import (
    _KST,
    _accumulate_sources,
    _format_with_citation_numbers,
    _select_answer_sources,
    _normalize_answer_format,
)
from app.rag.qdrant_chat import QdrantChatRetriever
from app.rag.multi_query_search import search_queries_in_parallel
from app.rag.query_expansion import QueryExpander
from app.rag.chat_router import is_architecture_question
from app.schemas.chat import ChatCommand, ChatResult, GeneratedChatAnswer

logger = logging.getLogger("uvicorn.error")


class SinglePassChatProvider:
    """결정적 검색 1회 → LLM 1회로 답하는 챗 provider(agentic 툴 루프 없음).

    질의 확장으로 멀티홉 단서를 한 번에 끌어와 컨텍스트에 담으므로, 루프 비결정성 없이
    빠르고 일관되게 답한다. 단 의미 검색만 하므로 날짜·건수·전체요약 질의는 다루지 않는다.
    """

    def __init__(
        self,
        *,
        structured_generation_port: StructuredGenerationPort,
        embedding_provider: EmbeddingProvider,
        retriever: QdrantChatRetriever,
        reranker: Reranker,
        model_profile: str,
        model_name: str,
        prompt_version: str,
        temperature: float = 0.2,
        candidate_pool: int = 30,
        top_n: int = 10,
        query_expander: QueryExpander | None = None,
        reasoning_budget: int | None = None,
    ) -> None:
        self._port = structured_generation_port
        self._embedding_provider = embedding_provider
        self._retriever = retriever
        self._reranker = reranker
        self._model_profile = model_profile
        self._model_name = model_name
        self._prompt_version = prompt_version
        self._temperature = temperature
        self._candidate_pool = candidate_pool
        self._top_n = top_n
        self._query_expander = query_expander
        self._reasoning_budget = reasoning_budget

    async def answer(self, command: ChatCommand) -> ChatResult:
        started_at = time.perf_counter()
        search_queries = [command.question]
        if self._query_expander is not None:
            search_queries = await self._query_expander.search_queries(command.question)
        expansion_finished_at = time.perf_counter()
        sources = await search_queries_in_parallel(
            queries=search_queries,
            command=command,
            embedding_provider=self._embedding_provider,
            retriever=self._retriever,
            reranker=self._reranker,
            source_types=None,
            candidate_pool=self._candidate_pool,
            top_n=self._top_n,
        )
        search_finished_at = time.perf_counter()
        if not sources:
            logger.info(
                "[single-pass] architecture=%s searches=%d kept=0 expansion_ms=%.1f "
                "search_ms=%.1f total_ms=%.1f",
                is_architecture_question(command.question),
                len(search_queries),
                (expansion_finished_at - started_at) * 1000,
                (search_finished_at - expansion_finished_at) * 1000,
                (search_finished_at - started_at) * 1000,
            )
            return ChatResult(
                answer="검색 가능한 자료에서 근거를 찾지 못했습니다.",
                sources=[],
                model=self._model_name,
                prompt_version=self._prompt_version,
            )

        accumulated: list = []
        _accumulate_sources(accumulated, sources)
        prompt = SINGLE_PASS_CHAT_PROMPT.format(
            today=datetime.now(_KST).date().isoformat(),
            documents=_format_with_citation_numbers(accumulated, sources),
            question=command.question,
        )
        architecture_question = is_architecture_question(command.question)
        result = await self._port.generate_structured(
            StructuredGenerationRequest(
                prompt=prompt,
                # 사용자에게 반환하는 계약은 항상 answer + citedIndices다. 설계 답변의
                # 섹션 구성은 prompt가 담당하며, 특정 주제의 불필요한 필드를 강제하지 않는다.
                response_schema=GeneratedChatAnswer,
                model_profile=self._model_profile,
                temperature=self._temperature,
                reasoning_budget=self._reasoning_budget,
            )
        )
        generation_finished_at = time.perf_counter()
        output = result.output
        answer = _normalize_answer_format(output.answer)
        logger.info(
            "[single-pass] architecture=%s searches=%d kept=%d expansion_ms=%.1f "
            "search_ms=%.1f generation_ms=%.1f total_ms=%.1f input_tokens=%s "
            "output_tokens=%s reasoning_tokens=%s",
            architecture_question,
            len(search_queries),
            len(sources),
            (expansion_finished_at - started_at) * 1000,
            (search_finished_at - expansion_finished_at) * 1000,
            (generation_finished_at - search_finished_at) * 1000,
            (generation_finished_at - started_at) * 1000,
            result.input_tokens,
            result.output_tokens,
            result.reasoning_tokens,
        )
        return ChatResult(
            answer=answer,
            sources=_select_answer_sources(
                accumulated,
                output.cited_indices,
                answer,
            ),
            model=result.model_name,
            prompt_version=self._prompt_version,
        )
