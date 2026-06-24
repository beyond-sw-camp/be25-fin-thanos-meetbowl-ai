from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class EmbeddingRequest:
    texts: list[str]
    model_profile: str


@dataclass(frozen=True)
class EmbeddingResult:
    embeddings: list[list[float]]
    model_name: str
    dimensions: int


class EmbeddingPort(Protocol):
    async def embed(self, request: EmbeddingRequest) -> EmbeddingResult: ...
