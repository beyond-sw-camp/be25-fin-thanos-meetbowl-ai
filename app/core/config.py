from functools import lru_cache
from urllib.parse import quote

from pydantic import PositiveInt, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.model_profiles import EmbeddingModelProfile, GenerationModelProfile


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    rabbitmq_enabled: bool = False
    rabbitmq_url: str | None = None
    rabbitmq_host: str = "localhost"
    rabbitmq_port: int = 5672
    rabbitmq_user: str = "meetbowl"
    rabbitmq_password: str = "local-rabbitmq-password"
    rabbitmq_vhost: str = "/"
    rabbitmq_exchange: str = "meetbowl.topic"
    rabbitmq_minutes_generate_queue: str = "ai.minutes.generate"
    rabbitmq_minutes_regenerate_queue: str = "ai.minutes.regenerate"
    rabbitmq_document_index_queue: str = "ai.index.document"
    rabbitmq_document_index_removed_queue: str = "ai.index.document.removed"
    rabbitmq_minutes_generated_routing_key: str = "minutes.generated"
    rabbitmq_max_retries: int = 3
    rabbitmq_prefetch_count: PositiveInt = 4
    rabbitmq_retry_base_delay_seconds: float = 2.0
    rabbitmq_retry_max_delay_seconds: float = 30.0
    rabbitmq_idempotency_ttl_seconds: int = 604800
    redis_feedback_enabled: bool = False
    redis_url: str = "redis://localhost:6379"
    redis_feedback_consumer_group: str = "ai-feedback"
    redis_feedback_consumer_name: str = "ai-local"
    redis_feedback_stream_max_length: int = 2000
    redis_feedback_scan_interval_seconds: float = 1.0
    gemini_api_key: str | None = None
    openai_api_key: str | None = None
    openai_base_url: str = "https://api.openai.com/v1"
    minutes_model_profile: str = "minutes-summary"
    minutes_summary_provider: str = "gemini"
    minutes_summary_model: str = "gemini-2.5-flash"
    minutes_summary_temperature: float = 0.2
    minutes_fallback_provider: str = "openai"
    minutes_fallback_model: str = "gpt-4.1-mini"
    chatbot_model_profile: str = "chatbot"
    # router = 질의별 분기(기본), single_pass = 검색1회+LLM1회(빠름, 의미검색만), agentic = LLM 툴 루프(느림/비결정적)
    chatbot_mode: str = "router"
    chatbot_provider: str = "gemini"
    chatbot_model: str = "gemini-2.5-flash"
    # 기본 모델이 503(과부하)일 때 자동 전환할 대체 모델. 같은 Gemini끼리는 과부하를 공유하므로
    # provider를 다르게(openai) 두면 Gemini 전체 장애 시에도 다른 벤더로 넘어가 응답을 살린다.
    chatbot_fallback_provider: str = "gemini"
    chatbot_fallback_model: str = "gemini-2.5-flash-lite"
    chatbot_temperature: float = 0.2
    # 검색 전 질의를 한↔영 번역·인명 음역으로 확장해 교차언어 검색을 결정적으로 만든다.
    query_expansion_enabled: bool = True
    query_expansion_model_profile: str = "query-expansion"
    query_expansion_provider: str = "gemini"
    query_expansion_model: str = "gemini-2.5-flash-lite"
    # 질의 확장·임베딩(질의만의 함수, 사용자 데이터 무관)을 캐시해 반복 검색의 LLM/임베딩 호출을 없앤다.
    chat_query_cache_enabled: bool = True
    chat_query_cache_max_size: int = 512
    chat_query_cache_ttl_seconds: float = 300.0
    document_embedding_model_profile: str = "document-embedding"
    document_embedding_provider: str = "openai"
    document_embedding_model: str = "text-embedding-3-large"
    document_embedding_dimensions: PositiveInt = 1536
    document_chunk_size: int = 1200
    document_chunk_overlap: int = 150
    document_chunk_strategy_version: str = "paragraph-v1"
    # 드라이브 파일(이미지/PDF) 텍스트 추출에 쓰는 Gemini 멀티모달 모델.
    document_extraction_model: str = "gemini-2.5-flash"
    # S3(드라이브 파일 저장소). 로컬은 LocalStack 엔드포인트, 운영은 None(실제 AWS).
    s3_endpoint: str | None = None
    s3_bucket: str = "meetbowl-files"
    aws_region: str = "ap-northeast-2"
    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None
    query_embedding_model_profile: str = "query-embedding"
    query_embedding_provider: str = "openai"
    query_embedding_model: str = "text-embedding-3-large"
    query_embedding_dimensions: PositiveInt = 1536
    gemini_model_name: str = "gemini-2.5-flash"
    gemini_temperature: float = 0.2
    fake_model_name: str = "fake-minutes-model"
    fake_chat_model_name: str = "fake-chat-model"
    fake_chat_rag_enabled: bool = False
    minutes_prompt_version: str = "minutes-v1"
    internal_token: str = "meetbowl-local-internal-token-32bytes"
    be_base_url: str = "http://localhost:8080"
    be_context_timeout_seconds: float = 5.0
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "meetbowl-documents-openai-large-1536"
    gemini_embedding_model_name: str = "gemini-embedding-001"
    chat_prompt_version: str = "chat-v9"
    chunk_max_chars: int = 1200
    chunk_overlap_chars: int = 150
    rerank_candidate_pool: int = 30
    rerank_top_n: int = 10
    # 챗봇 무근거 답변 차단: 리랭크 관련도(0~1)가 이 값 미만이면 출처에서 제외한다(0이면 비활성).
    chat_score_threshold: float = 0.0
    # 문서 전체 요약 시 본문 회수 상한(글자). 거대 문서가 토큰을 폭주시키지 않게 자른다.
    chat_document_max_chars: int = 16000
    # Gemini 사고(thinking) 토큰 예산. 256은 멀티홉 정답을 유지하면서 512 대비 지연을 줄인 측정값이다.
    chat_thinking_budget: int = 256
    # agentic 툴 루프 모델 호출 상한. 3이 정답률을 지키는 최소선이다(2는 멀티홉 단계 부족으로 붕괴).
    chat_request_limit: int = 3
    feedback_window_max_segments: int = 8
    feedback_window_max_seconds: int = 45
    feedback_min_segments: int = 4
    feedback_min_window_chars: int = 40
    feedback_trigger_interval_seconds: int = 15
    feedback_cooldown_seconds: int = 90
    feedback_state_ttl_seconds: int = 300
    feedback_score_threshold: float = 0.78
    feedback_candidate_limit: int = 3

    @model_validator(mode="after")
    def validate_unique_model_profiles(self) -> "Settings":
        profiles = self.generation_model_profiles()
        names = [profile.name for profile in profiles]
        if len(names) != len(set(names)):
            raise ValueError("Generation model profile names must be unique")
        embedding_profiles = self.embedding_model_profiles()
        embedding_names = [profile.name for profile in embedding_profiles]
        if len(embedding_names) != len(set(embedding_names)):
            raise ValueError("Embedding model profile names must be unique")
        document_profile, query_profile = embedding_profiles
        if (
            document_profile.provider,
            document_profile.model_name,
            document_profile.dimensions,
        ) != (
            query_profile.provider,
            query_profile.model_name,
            query_profile.dimensions,
        ):
            raise ValueError(
                "Document and query embedding provider/model/dimensions must match"
            )
        return self

    def generation_model_profiles(self) -> tuple[GenerationModelProfile, ...]:
        return (
            GenerationModelProfile(
                name=self.minutes_model_profile,
                provider=self.minutes_summary_provider,
                model_name=self.minutes_summary_model,
                temperature=self.minutes_summary_temperature,
            ),
            GenerationModelProfile(
                name=self.chatbot_model_profile,
                provider=self.chatbot_provider,
                model_name=self.chatbot_model,
                temperature=self.chatbot_temperature,
            ),
            GenerationModelProfile(
                name=self.query_expansion_model_profile,
                provider=self.query_expansion_provider,
                model_name=self.query_expansion_model,
                temperature=0.0,
            ),
        )

    def embedding_model_profiles(self) -> tuple[EmbeddingModelProfile, ...]:
        return (
            EmbeddingModelProfile(
                name=self.document_embedding_model_profile,
                provider=self.document_embedding_provider,
                model_name=self.document_embedding_model,
                dimensions=self.document_embedding_dimensions,
            ),
            EmbeddingModelProfile(
                name=self.query_embedding_model_profile,
                provider=self.query_embedding_provider,
                model_name=self.query_embedding_model,
                dimensions=self.query_embedding_dimensions,
            ),
        )

    def rabbitmq_connection_url(self) -> str:
        if self.rabbitmq_url:
            return self.rabbitmq_url
        user = quote(self.rabbitmq_user, safe="")
        password = quote(self.rabbitmq_password, safe="")
        if self.rabbitmq_vhost == "/":
            vhost = ""
        else:
            vhost = quote(self.rabbitmq_vhost.lstrip("/"), safe="")
        return (
            f"amqp://{user}:{password}@"
            f"{self.rabbitmq_host}:{self.rabbitmq_port}/{vhost}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
