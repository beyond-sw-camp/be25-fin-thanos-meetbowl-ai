import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.errors import ProviderUnavailableError, ResponseValidationError
from app.providers.gemini_llm import GeminiLLMProvider
from app.schemas.workflow import MinutesGenerationContext


class FakeModels:
    def __init__(self, text: str) -> None:
        self._text = text
        self.calls: list[dict] = []

    async def generate_content(self, **kwargs: object) -> SimpleNamespace:
        self.calls.append(kwargs)
        return SimpleNamespace(text=self._text)


def context() -> MinutesGenerationContext:
    return MinutesGenerationContext(
        meeting_id=uuid4(),
        organization_id=uuid4(),
        host_user_id=uuid4(),
        reviewer_user_id=uuid4(),
        title="배포 회의",
        started_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        ended_at=datetime(2026, 6, 1, 1, tzinfo=timezone.utc),
        raw_transcript="금요일 배포를 결정했습니다.",
    )


def test_gemini_provider_requests_and_validates_structured_output() -> None:
    models = FakeModels(
        '{"summary":"요약","agendaItems":[],"decisions":[],"actionItems":[]}'
    )
    client = SimpleNamespace(aio=SimpleNamespace(models=models))
    provider = GeminiLLMProvider(
        api_key=None,
        model_name="gemini-2.5-flash",
        temperature=0.2,
        client=client,
    )

    result = asyncio.run(provider.generate_minutes(prompt="prompt", context=context()))

    assert result["summary"] == "요약"
    assert models.calls[0]["model"] == "gemini-2.5-flash"
    assert models.calls[0]["config"].response_mime_type == "application/json"


def test_gemini_provider_requires_api_key_without_injected_client() -> None:
    provider = GeminiLLMProvider(
        api_key=None, model_name="gemini-2.5-flash", temperature=0.2
    )

    with pytest.raises(ProviderUnavailableError):
        asyncio.run(provider.generate_minutes(prompt="prompt", context=context()))


def test_gemini_provider_rejects_invalid_structured_response() -> None:
    models = FakeModels('{"summary":""}')
    client = SimpleNamespace(aio=SimpleNamespace(models=models))
    provider = GeminiLLMProvider(
        api_key=None,
        model_name="gemini-2.5-flash",
        temperature=0.2,
        client=client,
    )

    with pytest.raises(ResponseValidationError):
        asyncio.run(provider.generate_minutes(prompt="prompt", context=context()))
