import asyncio
from types import SimpleNamespace

import pytest

from app.core.errors import ProviderUnavailableError, ResponseValidationError
from app.ports.generation import StructuredGenerationRequest
from app.providers.gemini_generation import GeminiStructuredGenerationProvider
from app.schemas.minutes import MinutesDraft


class FakeModels:
    def __init__(self, text: str) -> None:
        self._text = text
        self.calls: list[dict] = []

    async def generate_content(self, **kwargs: object) -> SimpleNamespace:
        self.calls.append(kwargs)
        return SimpleNamespace(text=self._text)


def request() -> StructuredGenerationRequest:
    return StructuredGenerationRequest(
        prompt="prompt",
        response_schema=MinutesDraft,
        model_profile="minutes-summary",
    )


def test_gemini_provider_requests_and_validates_structured_output() -> None:
    models = FakeModels(
        '{"summary":"요약","agendaItems":[],"decisions":[],"actionItems":[]}'
    )
    client = SimpleNamespace(aio=SimpleNamespace(models=models))
    provider = GeminiStructuredGenerationProvider(
        api_key=None,
        model_name="gemini-2.5-flash",
        default_temperature=0.2,
        client=client,
    )

    result = asyncio.run(provider.generate_structured(request()))

    assert result.output.summary == "요약"
    assert result.model_name == "gemini-2.5-flash"
    assert models.calls[0]["model"] == "gemini-2.5-flash"
    assert models.calls[0]["config"].response_mime_type == "application/json"


def test_gemini_provider_requires_api_key_without_injected_client() -> None:
    provider = GeminiStructuredGenerationProvider(
        api_key=None, model_name="gemini-2.5-flash", default_temperature=0.2
    )

    with pytest.raises(ProviderUnavailableError):
        asyncio.run(provider.generate_structured(request()))


def test_gemini_provider_rejects_invalid_structured_response() -> None:
    models = FakeModels('{"summary":""}')
    client = SimpleNamespace(aio=SimpleNamespace(models=models))
    provider = GeminiStructuredGenerationProvider(
        api_key=None,
        model_name="gemini-2.5-flash",
        default_temperature=0.2,
        client=client,
    )

    with pytest.raises(ResponseValidationError):
        asyncio.run(provider.generate_structured(request()))
