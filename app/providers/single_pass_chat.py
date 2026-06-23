import logging
import json
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
    _select_cited_sources,
    _normalize_answer_format,
)
from app.rag.qdrant_chat import QdrantChatRetriever
from app.rag.multi_query_search import search_queries_in_parallel
from app.rag.query_expansion import QueryExpander
from app.rag.chat_router import is_architecture_question
from app.schemas.chat import ChatCommand, ChatResult, GeneratedChatAnswer
from app.schemas.chat import GeneratedArchitectureAnswer

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

    async def answer(self, command: ChatCommand) -> ChatResult:
        search_queries = [command.question]
        if self._query_expander is not None:
            search_queries = await self._query_expander.search_queries(command.question)
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
        logger.info(
            "[single-pass] query=%r searches=%r kept=%d",
            command.question,
            search_queries,
            len(sources),
        )
        if not sources:
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
        response_schema = (
            GeneratedArchitectureAnswer if architecture_question else GeneratedChatAnswer
        )
        result = await self._port.generate_structured(
            StructuredGenerationRequest(
                prompt=prompt,
                response_schema=response_schema,
                model_profile=self._model_profile,
                temperature=self._temperature,
            )
        )
        output = result.output
        if isinstance(output, GeneratedArchitectureAnswer):
            answer = _format_architecture_answer(output)
            cited_indices = output.cited_indices
        else:
            answer = output.answer
            cited_indices = output.cited_indices
        return ChatResult(
            answer=_normalize_answer_format(answer),
            sources=_select_cited_sources(accumulated, cited_indices),
            model=result.model_name,
            prompt_version=self._prompt_version,
        )


def _format_architecture_answer(output: GeneratedArchitectureAnswer) -> str:
    """구조화된 설계 응답을 사용자용 문서로 결정적으로 렌더링한다."""
    sections = [
        f"전체 처리 흐름\n{output.flow}",
        "구성요소별 책임\n"
        + "\n".join(
            f"- {item.name}: {item.responsibility}" for item in output.components
        ),
        "Harmony 메시지 구조\n"
        + "\n".join(
            f"- {item.role}: {item.purpose}" for item in output.harmony_roles
        )
        + f"\n- 포맷: {output.harmony_message_format}",
        "Safeguard 정책 구조\n"
        + "\n".join(
            f"- {item.name}: {item.purpose}"
            for item in output.safeguard_policy_sections
        ),
        "분류 결과 JSON 예시\n```json\n"
        + json.dumps(output.output_example.model_dump(), ensure_ascii=False, indent=2)
        + "\n```",
        f"Meetbowl 적용\n{output.meetbowl_application}",
        "주의점\n" + "\n".join(f"- {item}" for item in output.cautions),
    ]
    return "\n\n".join(sections)
