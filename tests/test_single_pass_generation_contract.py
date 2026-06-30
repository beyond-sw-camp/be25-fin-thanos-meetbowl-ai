"""single-pass 답변 생성의 최소 스키마와 reasoning 설정 검증."""

import asyncio
from uuid import uuid4

from app.ports.generation import StructuredGenerationResult
from app.providers.single_pass_chat import SinglePassChatProvider
from app.schemas.chat import ChatCommand, ChatSource, GeneratedChatAnswer


class _Embedding:
    async def embed(self, _text: str) -> list[float]:
        return [0.1]


class _Retriever:
    async def search(self, **_kwargs) -> list[ChatSource]:
        return [
            ChatSource(
                type="PERSONAL_MEMO",
                resource_id=uuid4(),
                title="설계 문서",
                snippet="처리 흐름과 구성요소 책임을 설명한다.",
                score=0.9,
            )
        ]


class _Reranker:
    async def rerank(self, *, query, sources, top_n):
        return sources[:top_n]


class _Generation:
    def __init__(self) -> None:
        self.request = None

    async def generate_structured(self, request):
        self.request = request
        return StructuredGenerationResult(
            output=GeneratedChatAnswer(answer="전체 처리 흐름", cited_indices=[1]),
            model_name="gemini-test",
        )


def test_architecture_question_uses_minimal_schema_and_reasoning_budget() -> None:
    generation = _Generation()
    provider = SinglePassChatProvider(
        structured_generation_port=generation,
        embedding_provider=_Embedding(),
        retriever=_Retriever(),
        reranker=_Reranker(),
        model_profile="chatbot",
        model_name="gemini-test",
        prompt_version="chat-test",
        reasoning_budget=128,
    )
    command = ChatCommand(
        request_id=uuid4(),
        correlation_id=uuid4(),
        user_id=uuid4(),
        question="내 프로젝트 아키텍처를 설계해줘",
    )

    result = asyncio.run(provider.answer(command))

    assert generation.request.response_schema is GeneratedChatAnswer
    assert generation.request.reasoning_budget == 128
    assert result.answer == "전체 처리 흐름"
    assert len(result.sources) == 1
