import logging
from dataclasses import dataclass

from pydantic_ai.models import Model
from pydantic_ai.models.fallback import FallbackModel
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.google import GoogleProvider
from pydantic_ai.providers.openai import OpenAIProvider

from app.core.config import Settings
from app.core.model_profiles import EmbeddingModelProfile, GenerationModelProfile
from app.ports.chat_provider import ChatProvider
from app.ports.embedding import EmbeddingPort, EmbeddingRequest
from app.ports.embedding_provider import EmbeddingProvider
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
from app.providers.fallback_structured_generation import FallbackStructuredGenerationProvider
from app.providers.openai_structured_generation import OpenAIStructuredGenerationProvider
from app.providers.vector_score_reranker import VectorScoreReranker
from app.providers.openai_embedding import OpenAIEmbeddingProvider
from app.providers.caching_embedding_provider import CachingEmbeddingProvider
from app.providers.pydantic_ai_chat import PydanticAiChatProvider
from app.providers.routing_chat import RoutingChatProvider
from app.providers.single_pass_chat import SinglePassChatProvider
from app.core.cache import AsyncResultCache
from app.rag.query_expansion import QueryExpander

logger = logging.getLogger("uvicorn.error")
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
    feedback_runtime_settings = settings.feedback_runtime_settings()
    generation_routes = {
        profile.name: _build_structured_generation_provider(profile, settings)
        for profile in settings.generation_model_profiles()
    }
    generation_routes[settings.minutes_model_profile] = _wrap_generation_fallback(
        primary=generation_routes[settings.minutes_model_profile],
        primary_provider=settings.minutes_summary_provider,
        fallback_provider=settings.minutes_fallback_provider,
        fallback_model=settings.minutes_fallback_model,
        fallback_temperature=settings.minutes_summary_temperature,
        settings=settings,
        route_name="minutes",
    )
    # 챗봇 답변 생성(single_pass)은 Gemini 503 시 OpenAI로 폴백시켜 agentic의 FallbackModel과 동일한 내구성을 준다.
    generation_routes[settings.chatbot_model_profile] = _wrap_generation_fallback(
        primary=generation_routes[settings.chatbot_model_profile],
        primary_provider=settings.chatbot_provider,
        fallback_provider=settings.chatbot_fallback_provider,
        fallback_model=settings.chatbot_fallback_model,
        fallback_temperature=settings.chatbot_temperature,
        settings=settings,
        route_name="chatbot",
    )
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
        chat_workflow=ChatWorkflow(
            _build_chat_provider(settings, embedding_port, structured_generation_port)
        ),
        meeting_feedback_workflow=MeetingFeedbackWorkflow(
            embedding_port=embedding_port,
            retriever=feedback_retriever,
            query_model_profile=settings.query_embedding_model_profile,
            score_threshold=feedback_runtime_settings.score_threshold,
            allow_semantic_fallback=feedback_runtime_settings.allow_semantic_fallback,
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


def _build_fallback_chat_model(
    settings: Settings, google_provider: GoogleProvider
) -> Model:
    """Gemini 기본 모델이 과부하일 때 넘어갈 대체 챗 모델을 provider 설정대로 만든다.

    같은 Gemini 모델끼리는 과부하(503)를 공유해 폴백 효과가 없으므로, openai로 두면
    Gemini 전역 장애에도 다른 벤더로 응답을 살릴 수 있다.
    """
    if settings.chatbot_fallback_provider in {"openai", "gpt"}:
        # 키 없이 OpenAI provider를 만들면 startup에서 즉시 예외가 나 앱 전체가 죽는다.
        # 키가 없으면 Gemini 대체 모델로 강등해 부팅은 살리되, 폴백 효과는 포기한다.
        if not settings.openai_api_key:
            logger.warning(
                "CHATBOT_FALLBACK_PROVIDER=openai이지만 OPENAI_API_KEY가 없어 "
                "Gemini 대체 모델(%s)로 강등합니다.",
                settings.chatbot_fallback_model,
            )
            return GoogleModel(settings.chatbot_model, provider=google_provider)
        return OpenAIChatModel(
            settings.chatbot_fallback_model,
            provider=OpenAIProvider(
                api_key=settings.openai_api_key,
                base_url=settings.openai_base_url,
            ),
        )
    return GoogleModel(settings.chatbot_fallback_model, provider=google_provider)


def _build_chat_provider(
    settings: Settings,
    embedding_port: EmbeddingPort,
    structured_generation_port: StructuredGenerationPort,
) -> ChatProvider:
    if settings.chatbot_provider == "gemini":
        google_provider = GoogleProvider(api_key=settings.gemini_api_key)
        expansion_cache: AsyncResultCache[list[str]] | None = None
        embedding_cache: AsyncResultCache[list[float]] | None = None
        if settings.chat_query_cache_enabled:
            expansion_cache = AsyncResultCache(
                max_size=settings.chat_query_cache_max_size,
                ttl_seconds=settings.chat_query_cache_ttl_seconds,
            )
            embedding_cache = AsyncResultCache(
                max_size=settings.chat_query_cache_max_size,
                ttl_seconds=settings.chat_query_cache_ttl_seconds,
            )
        query_expander = (
            QueryExpander(
                structured_generation_port=structured_generation_port,
                model_profile=settings.query_expansion_model_profile,
                cache=expansion_cache,
            )
            if settings.query_expansion_enabled
            else None
        )
        embedding_provider: EmbeddingProvider = _ProfileEmbeddingProviderAdapter(
            embedding_port=embedding_port,
            model_profile=settings.query_embedding_model_profile,
        )
        if embedding_cache is not None:
            embedding_provider = CachingEmbeddingProvider(embedding_provider, embedding_cache)
        retriever = QdrantChatRetriever(
            qdrant_url=settings.qdrant_url,
            qdrant_collection=settings.qdrant_collection,
        )
        # 벡터 점수 리랭커: 검색 단계 유사도 점수로만 재정렬해 검색마다 들던 Gemini 호출을 없앤다.
        reranker = VectorScoreReranker(score_threshold=settings.chat_score_threshold)

        def make_single_pass() -> SinglePassChatProvider:
            # 결정적 검색 1회 → LLM 1회. 루프 비결정성을 없애 멀티홉 일관성·속도를 노린다.
            return SinglePassChatProvider(
                structured_generation_port=structured_generation_port,
                embedding_provider=embedding_provider,
                retriever=retriever,
                reranker=reranker,
                model_profile=settings.chatbot_model_profile,
                model_name=settings.chatbot_model,
                prompt_version=settings.chat_prompt_version,
                temperature=settings.chatbot_temperature,
                candidate_pool=settings.rerank_candidate_pool,
                top_n=settings.rerank_top_n,
                query_expander=query_expander,
                reasoning_budget=settings.chat_thinking_budget,
            )

        def make_agentic() -> PydanticAiChatProvider:
            return PydanticAiChatProvider(
                # 기본 모델이 과부하(503)면 대체 모델로 자동 전환해 "그냥 멈춤"을 막는다.
                # 대체 모델은 provider를 다르게(openai) 둬 Gemini 전체 장애 시에도 응답을 살린다.
                model=FallbackModel(
                    GoogleModel(settings.chatbot_model, provider=google_provider),
                    _build_fallback_chat_model(settings, google_provider),
                ),
                embedding_provider=embedding_provider,
                retriever=retriever,
                reranker=reranker,
                model_name=settings.chatbot_model,
                prompt_version=settings.chat_prompt_version,
                temperature=settings.chatbot_temperature,
                candidate_pool=settings.rerank_candidate_pool,
                top_n=settings.rerank_top_n,
                document_max_chars=settings.chat_document_max_chars,
                thinking_budget=settings.chat_thinking_budget,
                request_limit=settings.chat_request_limit,
                query_expander=query_expander,
            )

        if settings.chatbot_mode == "single_pass":
            return make_single_pass()
        if settings.chatbot_mode == "router":
            # 내용·멀티홉은 single_pass, 날짜·건수·열거는 agentic으로 규칙 분기(지연 0).
            return RoutingChatProvider(
                single_pass=make_single_pass(), agentic=make_agentic()
            )
        return make_agentic()

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


def _wrap_generation_fallback(
    *,
    primary: StructuredGenerationPort,
    primary_provider: str,
    fallback_provider: str,
    fallback_model: str,
    fallback_temperature: float,
    settings: Settings,
    route_name: str,
) -> StructuredGenerationPort:
    if primary_provider != "gemini" or fallback_provider not in {"openai", "gpt"}:
        return primary
    if not settings.openai_api_key:
        logger.warning(
            "%s fallback provider is openai but OPENAI_API_KEY is missing; fallback disabled.",
            route_name,
        )
        return primary
    return FallbackStructuredGenerationProvider(
        primary=primary,
        fallback=OpenAIStructuredGenerationProvider(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            model_name=fallback_model,
            default_temperature=fallback_temperature,
        ),
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
    if profile.provider in {"openai", "gpt"}:
        return OpenAIStructuredGenerationProvider(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
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
