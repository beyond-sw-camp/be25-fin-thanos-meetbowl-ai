from dataclasses import dataclass

from pydantic_ai.models.google import GoogleModel
from pydantic_ai.providers.google import GoogleProvider

from app.core.config import Settings
from app.providers.fake_context_loader import FakeMinutesContextLoader
from app.providers.fake_chat import FakeChatProvider
from app.providers.fake_embedding import FakeEmbeddingProvider
from app.providers.fake_llm import FakeLLMProvider
from app.providers.fake_reranker import FakeReranker
from app.providers.gemini_embedding import GeminiEmbeddingProvider
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
            llm_provider=llm_provider,
            prompt_version=settings.minutes_prompt_version,
        ),
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
