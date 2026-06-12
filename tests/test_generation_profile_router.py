import asyncio

import pytest
from pydantic import BaseModel

from app.container import build_container
from app.core.config import Settings
from app.core.errors import ModelProfileNotConfiguredError
from app.ports.generation import (
    StructuredGenerationRequest,
    StructuredGenerationResult,
)
from app.providers.structured_generation_router import (
    ProfileRoutingStructuredGenerationProvider,
)


class Output(BaseModel):
    value: str


class CapturingProvider:
    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        self.calls = 0

    async def generate_structured(
        self, request: StructuredGenerationRequest
    ) -> StructuredGenerationResult:
        self.calls += 1
        return StructuredGenerationResult(
            output=request.response_schema(value=request.model_profile),
            model_name=self.model_name,
        )


def request(model_profile: str) -> StructuredGenerationRequest:
    return StructuredGenerationRequest(
        prompt="prompt",
        response_schema=Output,
        model_profile=model_profile,
    )


def test_router_selects_provider_by_model_profile() -> None:
    minutes = CapturingProvider("minutes-model")
    chatbot = CapturingProvider("chatbot-model")
    router = ProfileRoutingStructuredGenerationProvider(
        {"minutes-summary": minutes, "chatbot": chatbot}
    )

    minutes_result = asyncio.run(router.generate_structured(request("minutes-summary")))
    chatbot_result = asyncio.run(router.generate_structured(request("chatbot")))

    assert minutes_result.model_name == "minutes-model"
    assert chatbot_result.model_name == "chatbot-model"
    assert minutes.calls == 1
    assert chatbot.calls == 1


def test_router_rejects_unknown_model_profile() -> None:
    router = ProfileRoutingStructuredGenerationProvider({})

    with pytest.raises(ModelProfileNotConfiguredError):
        asyncio.run(router.generate_structured(request("unknown")))


def test_settings_reject_duplicate_model_profile_names() -> None:
    with pytest.raises(ValueError, match="profile names must be unique"):
        Settings(chatbot_model_profile="minutes-summary")


def test_settings_reject_duplicate_embedding_profile_names() -> None:
    with pytest.raises(ValueError, match="Embedding model profile names must be unique"):
        Settings(query_embedding_model_profile="document-embedding")


def test_settings_build_independent_generation_profiles() -> None:
    settings = Settings(
        minutes_summary_model="minutes-model",
        chatbot_model="chat-model",
        meeting_feedback_model="feedback-model",
    )

    profiles = {
        profile.name: profile for profile in settings.generation_model_profiles()
    }

    assert profiles["minutes-summary"].model_name == "minutes-model"
    assert profiles["chatbot"].model_name == "chat-model"
    assert profiles["meeting-feedback"].model_name == "feedback-model"


def test_settings_build_independent_embedding_profiles() -> None:
    settings = Settings(
        document_embedding_model="document-model",
        query_embedding_model="query-model",
    )

    profiles = {
        profile.name: profile for profile in settings.embedding_model_profiles()
    }

    assert profiles["document-embedding"].model_name == "document-model"
    assert profiles["query-embedding"].model_name == "query-model"


def test_settings_default_embedding_provider_is_openai() -> None:
    settings = Settings(_env_file=None)

    profiles = {
        profile.name: profile for profile in settings.embedding_model_profiles()
    }

    assert profiles["document-embedding"].provider == "openai"
    assert profiles["query-embedding"].provider == "openai"


def test_container_rejects_unsupported_generation_provider_at_startup() -> None:
    settings = Settings(minutes_summary_provider="unsupported")

    with pytest.raises(ValueError, match="minutes-summary: unsupported"):
        build_container(settings)
