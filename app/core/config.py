from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    rabbitmq_enabled: bool = False
    rabbitmq_url: str = "amqp://meetbowl:local-rabbitmq-password@localhost:5672/"
    rabbitmq_exchange: str = "meetbowl.topic"
    rabbitmq_minutes_generate_queue: str = "ai.minutes.generate"
    rabbitmq_minutes_regenerate_queue: str = "ai.minutes.regenerate"
    rabbitmq_minutes_generated_routing_key: str = "minutes.generated"
    rabbitmq_max_retries: int = 3
    llm_provider: str = "gemini"
    gemini_api_key: str | None = None
    gemini_model_name: str = "gemini-2.5-flash"
    gemini_temperature: float = 0.2
    fake_model_name: str = "fake-minutes-model"
    minutes_prompt_version: str = "minutes-v1"
    internal_token: str = "meetbowl-local-internal-token-32bytes"
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "meetbowl-documents"
    gemini_embedding_model_name: str = "text-embedding-004"
    chat_prompt_version: str = "chat-v1"


@lru_cache
def get_settings() -> Settings:
    return Settings()
