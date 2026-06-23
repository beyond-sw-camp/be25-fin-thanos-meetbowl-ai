"""구조화 생성 폴백: 기본이 불가하면 대체로 넘기고, 정상이면 대체를 안 부른다."""

import asyncio

from app.core.errors import ProviderUnavailableError
from app.ports.generation import StructuredGenerationRequest, StructuredGenerationResult
from app.providers.fallback_structured_generation import (
    FallbackStructuredGenerationProvider,
)
from app.schemas.chat import GeneratedChatAnswer


class _Stub:
    def __init__(self, *, name: str, fail: bool = False) -> None:
        self.name = name
        self.fail = fail
        self.calls = 0

    async def generate_structured(self, request: StructuredGenerationRequest):
        self.calls += 1
        if self.fail:
            raise ProviderUnavailableError(f"{self.name} unavailable")
        return StructuredGenerationResult(
            output=GeneratedChatAnswer(answer=self.name, cited_indices=[]),
            model_name=self.name,
        )


def _request() -> StructuredGenerationRequest:
    return StructuredGenerationRequest(
        prompt="q", response_schema=GeneratedChatAnswer, model_profile="chatbot"
    )


def test_falls_back_when_primary_unavailable() -> None:
    primary = _Stub(name="gemini", fail=True)
    fallback = _Stub(name="openai")
    provider = FallbackStructuredGenerationProvider(primary=primary, fallback=fallback)

    result = asyncio.run(provider.generate_structured(_request()))

    assert result.model_name == "openai"
    assert primary.calls == 1 and fallback.calls == 1


def test_skips_fallback_when_primary_ok() -> None:
    primary = _Stub(name="gemini")
    fallback = _Stub(name="openai")
    provider = FallbackStructuredGenerationProvider(primary=primary, fallback=fallback)

    result = asyncio.run(provider.generate_structured(_request()))

    assert result.model_name == "gemini"
    assert fallback.calls == 0
