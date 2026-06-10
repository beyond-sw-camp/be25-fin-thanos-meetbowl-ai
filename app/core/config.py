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
    structured_generation_provider: str = "gemini"
    gemini_api_key: str | None = None
    gemini_model_name: str = "gemini-2.5-flash"
    gemini_temperature: float = 0.2
    fake_model_name: str = "fake-minutes-model"
    minutes_model_profile: str = "minutes-summary"
    minutes_prompt_version: str = "minutes-v1"


@lru_cache
def get_settings() -> Settings:
    return Settings()
