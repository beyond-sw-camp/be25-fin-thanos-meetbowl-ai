from dataclasses import dataclass

from app.core.config import Settings
from app.providers.fake_context_loader import FakeMinutesContextLoader
from app.providers.fake_llm import FakeLLMProvider
from app.providers.gemini_llm import GeminiLLMProvider
from app.workflows.minutes_generation import MinutesGenerationWorkflow


@dataclass(frozen=True)
class Container:
    minutes_workflow: MinutesGenerationWorkflow


def build_container(settings: Settings) -> Container:
    if settings.llm_provider == "gemini":
        llm_provider = GeminiLLMProvider(
            api_key=settings.gemini_api_key,
            model_name=settings.gemini_model_name,
            temperature=settings.gemini_temperature,
        )
    elif settings.llm_provider == "fake":
        llm_provider = FakeLLMProvider(settings.fake_model_name)
    else:
        raise ValueError(f"Unsupported LLM_PROVIDER: {settings.llm_provider}")

    return Container(
        minutes_workflow=MinutesGenerationWorkflow(
            context_loader=FakeMinutesContextLoader(),
            llm_provider=llm_provider,
            prompt_version=settings.minutes_prompt_version,
        )
    )
