"""Gemini 구조화 생성 설정과 사용량 계측 검증."""

import asyncio

from app.ports.generation import StructuredGenerationRequest
from app.providers.gemini_generation import GeminiStructuredGenerationProvider
from app.schemas.chat import GeneratedChatAnswer


class _Usage:
    prompt_token_count = 120
    candidates_token_count = 35
    thoughts_token_count = 17


class _Response:
    text = '{"answer":"ok","citedIndices":[1]}'
    usage_metadata = _Usage()


class _Models:
    def __init__(self) -> None:
        self.config = None

    async def generate_content(self, *, model, contents, config):
        self.config = config
        return _Response()


class _Client:
    def __init__(self) -> None:
        self.aio = type("Aio", (), {})()
        self.aio.models = _Models()


def test_applies_reasoning_budget_and_returns_usage() -> None:
    client = _Client()
    provider = GeminiStructuredGenerationProvider(
        api_key=None,
        model_name="gemini-test",
        default_temperature=0.2,
        client=client,
    )

    result = asyncio.run(
        provider.generate_structured(
            StructuredGenerationRequest(
                prompt="q",
                response_schema=GeneratedChatAnswer,
                model_profile="chatbot",
                reasoning_budget=128,
            )
        )
    )

    assert client.aio.models.config.thinking_config.thinking_budget == 128
    assert result.input_tokens == 120
    assert result.output_tokens == 35
    assert result.reasoning_tokens == 17


def test_omits_thinking_config_when_budget_is_unspecified() -> None:
    client = _Client()
    provider = GeminiStructuredGenerationProvider(
        api_key=None,
        model_name="gemini-test",
        default_temperature=0.2,
        client=client,
    )

    asyncio.run(
        provider.generate_structured(
            StructuredGenerationRequest(
                prompt="q",
                response_schema=GeneratedChatAnswer,
                model_profile="chatbot",
            )
        )
    )

    assert client.aio.models.config.thinking_config is None
