from dataclasses import dataclass

from pydantic_ai.models.google import GoogleModel
from pydantic_ai.providers.google import GoogleProvider

from app.core.config import Settings
from app.core.model_profiles import EmbeddingModelProfile, GenerationModelProfile
from app.ports.chat_provider import ChatProvider
from app.ports.embedding import EmbeddingPort, EmbeddingRequest
from app.ports.generation import StructuredGenerationPort
from app.providers.embedding_router import ProfileRoutingEmbeddingProvider
from app.providers.fake_chat import FakeChatProvider
from app.providers.http_minutes_context_loader import HttpMinutesContextLoader
from app.providers.fake_embedding import FakeEmbeddingProvider
from app.providers.fake_generation import FakeStructuredGenerationProvider
from app.providers.fake_reranker import FakeReranker
from app.pipelines.file_text_extraction import FileTextExtractor
from app.providers.gemini_embedding import GeminiEmbeddingProvider
from app.providers.gemini_extraction import GeminiFileExtractor
from app.providers.gemini_generation import GeminiStructuredGenerationProvider
from app.providers.gemini_reranker import GeminiReranker
from app.providers.openai_embedding import OpenAIEmbeddingProvider
from app.providers.pydantic_ai_chat import PydanticAiChatProvider
from app.providers.s3_file_storage import S3FileStorage
from app.providers.structured_generation_router import (
    ProfileRoutingStructuredGenerationProvider,
)
from app.rag.qdrant_feedback import QdrantMeetingFeedbackRetriever
from app.rag.qdrant_chat import QdrantChatRetriever
from app.rag.qdrant_vector_store import QdrantVectorStore
from app.workflows.chat import ChatWorkflow
from app.workflows.document_indexing import DocumentIndexingWorkflow
from app.workflows.meeting_feedback import MeetingFeedbackWorkflow
from app.workflows.minutes_generation import MinutesGenerationWorkflow


@dataclass(frozen=True)
class Container:
    minutes_workflow: MinutesGenerationWorkflow
    document_indexing_workflow: DocumentIndexingWorkflow
    chat_workflow: ChatWorkflow
    meeting_feedback_workflow: MeetingFeedbackWorkflow
    qdrant_vector_store: QdrantVectorStore


def build_container(settings: Settings) -> Container:
    generation_routes = {
        profile.name: _build_structured_generation_provider(profile, settings)
        for profile in settings.generation_model_profiles()
    }
    structured_generation_port = ProfileRoutingStructuredGenerationProvider(
        generation_routes
    )
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
    feedback_retriever = QdrantMeetingFeedbackRetriever(
        qdrant_url=settings.qdrant_url,
        qdrant_collection=settings.qdrant_collection,
        candidate_limit=settings.feedback_candidate_limit,
    )
    return Container(
        minutes_workflow=MinutesGenerationWorkflow(
            context_loader=HttpMinutesContextLoader(
                base_url=settings.be_base_url,
                internal_token=settings.internal_token,
                timeout_seconds=settings.be_context_timeout_seconds,
            ),
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
            # 드라이브 파일(이미지/PDF)은 S3에서 받아 텍스트를 추출한 뒤 색인한다.
            file_storage_port=S3FileStorage(
                bucket=settings.s3_bucket,
                region=settings.aws_region,
                endpoint_url=settings.s3_endpoint,
                access_key_id=settings.aws_access_key_id,
                secret_access_key=settings.aws_secret_access_key,
            ),
            file_text_extractor=FileTextExtractor(
                gemini_extractor=GeminiFileExtractor(
                    api_key=settings.gemini_api_key,
                    model_name=settings.document_extraction_model,
                )
            ),
        ),
        chat_workflow=ChatWorkflow(_build_chat_provider(settings, embedding_port)),
        meeting_feedback_workflow=MeetingFeedbackWorkflow(
            embedding_port=embedding_port,
            retriever=feedback_retriever,
            query_model_profile=settings.query_embedding_model_profile,
            score_threshold=settings.feedback_score_threshold,
        ),
        qdrant_vector_store=qdrant_vector_store,
    )


class _ProfileEmbeddingProviderAdapter:
    """챗봇 검색용 단건 임베딩 요청을 profile 기반 EmbeddingPort 호출로 변환한다."""

    def __init__(self, *, embedding_port: EmbeddingPort, model_profile: str) -> None:
        self._embedding_port = embedding_port
        self._model_profile = model_profile

    async def embed(self, text: str) -> list[float]:
        result = await self._embedding_port.embed(
            EmbeddingRequest(texts=[text], model_profile=self._model_profile)
        )
        return result.embeddings[0]


def _build_chat_provider(
    settings: Settings, embedding_port: EmbeddingPort
) -> ChatProvider:
    if settings.chatbot_provider == "gemini":
        return PydanticAiChatProvider(
            model=GoogleModel(
                settings.chatbot_model,
                provider=GoogleProvider(api_key=settings.gemini_api_key),
            ),
            embedding_provider=_ProfileEmbeddingProviderAdapter(
                embedding_port=embedding_port,
                model_profile=settings.query_embedding_model_profile,
            ),
            retriever=QdrantChatRetriever(
                qdrant_url=settings.qdrant_url,
                qdrant_collection=settings.qdrant_collection,
            ),
            reranker=GeminiReranker(
                api_key=settings.gemini_api_key,
                model_name=settings.chatbot_model,
                score_threshold=settings.chat_score_threshold,
                thinking_budget=settings.chat_thinking_budget,
            ),
            model_name=settings.chatbot_model,
            prompt_version=settings.chat_prompt_version,
            temperature=settings.chatbot_temperature,
            candidate_pool=settings.rerank_candidate_pool,
            top_n=settings.rerank_top_n,
            document_max_chars=settings.chat_document_max_chars,
            thinking_budget=settings.chat_thinking_budget,
        )

    chat_provider_kwargs: dict = {}
    if settings.fake_chat_rag_enabled:
        # fake 챗봇 모드는 외부 LLM 없이 색인·권한 필터·검색 연결성을 검증하기 위한 경로다.
        chat_provider_kwargs = {
            "embedding_provider": _ProfileEmbeddingProviderAdapter(
                embedding_port=embedding_port,
                model_profile=settings.query_embedding_model_profile,
            ),
            "retriever": QdrantChatRetriever(
                qdrant_url=settings.qdrant_url,
                qdrant_collection=settings.qdrant_collection,
            ),
            "reranker": FakeReranker(score_threshold=settings.chat_score_threshold),
            "top_n": settings.rerank_top_n,
        }
    return FakeChatProvider(
        model_name=settings.fake_chat_model_name,
        prompt_version=settings.chat_prompt_version,
        **chat_provider_kwargs,
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
            dimensions=profile.dimensions,
        )
    if profile.provider == "fake":
        return FakeEmbeddingProvider(profile.model_name, profile.dimensions or 4)
    raise ValueError(
        f"Unsupported embedding provider for profile {profile.name}: {profile.provider}"
    )
