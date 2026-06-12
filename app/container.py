from dataclasses import dataclass

from app.core.config import Settings
from app.core.model_profiles import EmbeddingModelProfile, GenerationModelProfile
from app.ports.embedding import EmbeddingPort
from app.ports.generation import StructuredGenerationPort
from app.providers.embedding_router import ProfileRoutingEmbeddingProvider
from app.providers.fake_embedding import FakeEmbeddingProvider
from app.providers.fake_context_loader import FakeMinutesContextLoader
from app.providers.gemini_embedding import GeminiEmbeddingProvider
from app.providers.fake_generation import FakeStructuredGenerationProvider
from app.providers.openai_embedding import OpenAIEmbeddingProvider
from app.providers.gemini_generation import GeminiStructuredGenerationProvider
from app.providers.structured_generation_router import (
    ProfileRoutingStructuredGenerationProvider,
)
from app.rag.qdrant_vector_store import QdrantVectorStore
from app.workflows.document_indexing import DocumentIndexingWorkflow
from app.workflows.minutes_generation import MinutesGenerationWorkflow


@dataclass(frozen=True)
class Container:
    minutes_workflow: MinutesGenerationWorkflow
    document_indexing_workflow: DocumentIndexingWorkflow
    qdrant_vector_store: QdrantVectorStore


def build_container(settings: Settings) -> Container:
    routes = {
        profile.name: _build_structured_generation_provider(profile, settings)
        for profile in settings.generation_model_profiles()
    }
    structured_generation_port = ProfileRoutingStructuredGenerationProvider(routes)
    embedding_port = ProfileRoutingEmbeddingProvider(
        {
            profile.name: _build_embedding_provider(profile, settings)
            for profile in settings.embedding_model_profiles()
        }
    )
    qdrant_vector_store = QdrantVectorStore(
        base_url=settings.qdrant_url,
        collection_name=settings.qdrant_collection,
    )

    return Container(
        minutes_workflow=MinutesGenerationWorkflow(
            context_loader=FakeMinutesContextLoader(),
            structured_generation_port=structured_generation_port,
            model_profile=settings.minutes_model_profile,
            prompt_version=settings.minutes_prompt_version,
        ),
        document_indexing_workflow=DocumentIndexingWorkflow(
            embedding_port=embedding_port,
            vector_store_port=qdrant_vector_store,
            model_profile=settings.document_embedding_model_profile,
            chunk_size=settings.document_chunk_size,
            chunk_overlap=settings.document_chunk_overlap,
            chunk_strategy_version=settings.document_chunk_strategy_version,
        ),
        qdrant_vector_store=qdrant_vector_store,
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


def _build_embedding_provider(
    profile: EmbeddingModelProfile, settings: Settings
) -> EmbeddingPort:
    if profile.provider == "gemini":
        return GeminiEmbeddingProvider(
            api_key=settings.gemini_api_key,
            model_name=profile.model_name,
        )
    if profile.provider in {"openai", "gpt"}:
        return OpenAIEmbeddingProvider(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            model_name=profile.model_name,
        )
    if profile.provider == "fake":
        return FakeEmbeddingProvider(profile.model_name)
    raise ValueError(
        f"Unsupported embedding provider for profile {profile.name}: {profile.provider}"
    )
