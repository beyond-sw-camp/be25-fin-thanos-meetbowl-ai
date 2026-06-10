from dataclasses import dataclass

from app.core.config import Settings
from app.providers.fake_context_loader import FakeMinutesContextLoader
from app.providers.fake_generation import FakeStructuredGenerationProvider
from app.providers.gemini_generation import GeminiStructuredGenerationProvider
from app.workflows.minutes_generation import MinutesGenerationWorkflow


@dataclass(frozen=True)
class Container:
    minutes_workflow: MinutesGenerationWorkflow


def build_container(settings: Settings) -> Container:
    if settings.structured_generation_provider == "gemini":
        structured_generation_port = GeminiStructuredGenerationProvider(
            api_key=settings.gemini_api_key,
            model_name=settings.gemini_model_name,
            default_temperature=settings.gemini_temperature,
        )
    elif settings.structured_generation_provider == "fake":
        structured_generation_port = FakeStructuredGenerationProvider(
            settings.fake_model_name
        )
    else:
        raise ValueError(
            "Unsupported STRUCTURED_GENERATION_PROVIDER: "
            f"{settings.structured_generation_provider}"
        )

    return Container(
        minutes_workflow=MinutesGenerationWorkflow(
            context_loader=FakeMinutesContextLoader(),
            structured_generation_port=structured_generation_port,
            model_profile=settings.minutes_model_profile,
            prompt_version=settings.minutes_prompt_version,
        )
    )
