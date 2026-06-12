from dataclasses import dataclass

from pydantic_ai.models.google import GoogleModel
from pydantic_ai.providers.google import GoogleProvider

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
from app.providers.fake_chat import FakeChatProvider
from app.providers.fake_llm import FakeLLMProvider
from app.providers.fake_reranker import FakeReranker
from app.providers.gemini_llm import GeminiLLMProvider
from app.providers.gemini_reranker import GeminiReranker
from app.providers.pydantic_ai_chat import PydanticAiChatProvider
from app.rag.qdrant_chat import QdrantChatRetriever
from app.rag.qdrant_index import QdrantDocumentIndexer
from app.workflows.chat import ChatWorkflow
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
    chat_workflow: ChatWorkflow
    document_indexing_workflow: DocumentIndexingWorkflow


def build_container(settings: Settings) -> Container:
    if settings.llm_provider == "gemini":
        embedding_provider = GeminiEmbeddingProvider(
            api_key=settings.gemini_api_key,
            model_name=settings.gemini_embedding_model_name,
        )
        llm_provider = GeminiLLMProvider(
            api_key=settings.gemini_api_key,
            model_name=settings.gemini_model_name,
            temperature=settings.gemini_temperature,
        )
        chat_model = GoogleModel(
            settings.gemini_model_name,
            provider=GoogleProvider(api_key=settings.gemini_api_key),
        )
        chat_provider = PydanticAiChatProvider(
            model=chat_model,
            embedding_provider=embedding_provider,
            retriever=QdrantChatRetriever(
                qdrant_url=settings.qdrant_url,
                qdrant_collection=settings.qdrant_collection,
            ),
            reranker=GeminiReranker(
                api_key=settings.gemini_api_key,
                model_name=settings.gemini_model_name,
            ),
            model_name=settings.gemini_model_name,
            prompt_version=settings.chat_prompt_version,
            temperature=settings.gemini_temperature,
            candidate_pool=settings.rerank_candidate_pool,
            top_n=settings.rerank_top_n,
        )
    elif settings.llm_provider == "fake":
        embedding_provider = FakeEmbeddingProvider()
        llm_provider = FakeLLMProvider(settings.fake_model_name)
        chat_provider = FakeChatProvider(
            settings.fake_chat_model_name,
            settings.chat_prompt_version,
            embedding_provider=embedding_provider if settings.fake_chat_rag_enabled else None,
            retriever=(
                QdrantChatRetriever(
                    qdrant_url=settings.qdrant_url,
                    qdrant_collection=settings.qdrant_collection,
                )
                if settings.fake_chat_rag_enabled
                else None
            ),
            reranker=FakeReranker() if settings.fake_chat_rag_enabled else None,
            top_n=settings.rerank_top_n,
        )
    else:
        raise ValueError(f"Unsupported LLM_PROVIDER: {settings.llm_provider}")

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
        chat_workflow=ChatWorkflow(chat_provider),
        document_indexing_workflow=DocumentIndexingWorkflow(
            embedding_provider=embedding_provider,
            indexer=QdrantDocumentIndexer(
                qdrant_url=settings.qdrant_url,
                qdrant_collection=settings.qdrant_collection,
            ),
            chunk_max_chars=settings.chunk_max_chars,
            chunk_overlap_chars=settings.chunk_overlap_chars,
        ),
    )
