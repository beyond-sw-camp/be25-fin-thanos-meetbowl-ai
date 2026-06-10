from dataclasses import dataclass


@dataclass(frozen=True)
class GenerationModelProfile:
    name: str
    provider: str
    model_name: str
    temperature: float


@dataclass(frozen=True)
class EmbeddingModelProfile:
    name: str
    provider: str
    model_name: str
