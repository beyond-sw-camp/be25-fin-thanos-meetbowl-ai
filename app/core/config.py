from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.model_profiles import EmbeddingModelProfile, GenerationModelProfile


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    rabbitmq_enabled: bool = False
    rabbitmq_url: str = "amqp://meetbowl:local-rabbitmq-password@localhost:5672/"
    rabbitmq_exchange: str = "meetbowl.topic"
    rabbitmq_minutes_generate_queue: str = "ai.minutes.generate"
    rabbitmq_minutes_regenerate_queue: str = "ai.minutes.regenerate"
    rabbitmq_document_index_queue: str = "ai.index.document"
    rabbitmq_minutes_generated_routing_key: str = "minutes.generated"
    rabbitmq_max_retries: int = 3
    gemini_api_key: str | None = None
    openai_api_key: str | None = None
    openai_base_url: str = "https://api.openai.com/v1"
    minutes_model_profile: str = "minutes-summary"
    minutes_summary_provider: str = "gemini"
    minutes_summary_model: str = "gemini-2.5-flash"
    minutes_summary_temperature: float = 0.2
    chatbot_model_profile: str = "chatbot"
    chatbot_provider: str = "gemini"
    chatbot_model: str = "gemini-2.5-flash"
    chatbot_temperature: float = 0.2
    meeting_feedback_model_profile: str = "meeting-feedback"
    meeting_feedback_provider: str = "gemini"
    meeting_feedback_model: str = "gemini-2.5-flash"
    meeting_feedback_temperature: float = 0.2
    document_embedding_model_profile: str = "document-embedding"
    document_embedding_provider: str = "openai"
    document_embedding_model: str = "text-embedding-3-large"
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "meetbowl_documents_v1"
    document_chunk_size: int = 1200
    document_chunk_overlap: int = 150
    document_chunk_strategy_version: str = "paragraph-v1"
    query_embedding_model_profile: str = "query-embedding"
    query_embedding_provider: str = "openai"
    query_embedding_model: str = "text-embedding-3-large"
    gemini_model_name: str = "gemini-2.5-flash"
    gemini_temperature: float = 0.2
    fake_model_name: str = "fake-minutes-model"
    fake_chat_model_name: str = "fake-chat-model"
    fake_chat_rag_enabled: bool = False
    minutes_prompt_version: str = "minutes-v1"
    internal_token: str = "meetbowl-local-internal-token-32bytes"
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "meetbowl-documents-gemini"
    gemini_embedding_model_name: str = "gemini-embedding-001"
    chat_prompt_version: str = "chat-v1"
    chunk_max_chars: int = 1200
    chunk_overlap_chars: int = 150
    rerank_candidate_pool: int = 30
    rerank_top_n: int = 10

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
                name=self.meeting_feedback_model_profile,
                provider=self.meeting_feedback_provider,
                model_name=self.meeting_feedback_model,
                temperature=self.meeting_feedback_temperature,
            ),
        )

    def embedding_model_profiles(self) -> tuple[EmbeddingModelProfile, ...]:
        return (
            EmbeddingModelProfile(
                name=self.document_embedding_model_profile,
                provider=self.document_embedding_provider,
                model_name=self.document_embedding_model,
            ),
            EmbeddingModelProfile(
                name=self.query_embedding_model_profile,
                provider=self.query_embedding_provider,
                model_name=self.query_embedding_model,
            ),
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
