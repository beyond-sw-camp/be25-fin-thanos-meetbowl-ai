from dataclasses import dataclass

from app.core.config import Settings
from app.core.model_profiles import GenerationModelProfile
from app.ports.generation import StructuredGenerationPort
from app.providers.fake_context_loader import FakeMinutesContextLoader
from app.providers.fake_generation import FakeStructuredGenerationProvider
from app.providers.gemini_generation import GeminiStructuredGenerationProvider
from app.providers.structured_generation_router import (
    ProfileRoutingStructuredGenerationProvider,
)
from app.workflows.minutes_generation import MinutesGenerationWorkflow


@dataclass(frozen=True)
class Container:
    minutes_workflow: MinutesGenerationWorkflow


def build_container(settings: Settings) -> Container:
    routes = {
        profile.name: _build_structured_generation_provider(profile, settings)
        for profile in settings.generation_model_profiles()
    }
    structured_generation_port = ProfileRoutingStructuredGenerationProvider(routes)

    return Container(
        minutes_workflow=MinutesGenerationWorkflow(
            context_loader=FakeMinutesContextLoader(),
            structured_generation_port=structured_generation_port,
            model_profile=settings.minutes_model_profile,
            prompt_version=settings.minutes_prompt_version,
        )
    )


def _build_structured_generation_provider(
    profile: GenerationModelProfile, settings: Settings
) -> StructuredGenerationPort:
    if profile.provider == "gemini":
        return GeminiStructuredGenerationProvider(
            api_key=settings.gemini_api_key,
            model_name=profile.model_name,
            default_temperature=profile.temperature,
        )
    if profile.provider == "fake":
        return FakeStructuredGenerationProvider(profile.model_name)
    raise ValueError(
        f"Unsupported generation provider for profile {profile.name}: {profile.provider}"
    )
