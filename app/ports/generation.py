from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Generic, Protocol, TypeVar

from pydantic import BaseModel

StructuredOutput = TypeVar("StructuredOutput", bound=BaseModel)


@dataclass(frozen=True)
class TextGenerationRequest:
    prompt: str
    model_profile: str
    temperature: float | None = None


@dataclass(frozen=True)
class TextGenerationResult:
    text: str
    model_name: str


@dataclass(frozen=True)
class StructuredGenerationRequest(Generic[StructuredOutput]):
    prompt: str
    response_schema: type[StructuredOutput]
    model_profile: str
    temperature: float | None = None


@dataclass(frozen=True)
class StructuredGenerationResult(Generic[StructuredOutput]):
    output: StructuredOutput
    model_name: str


class TextGenerationPort(Protocol):
    async def generate(self, request: TextGenerationRequest) -> TextGenerationResult: ...


class StreamingGenerationPort(Protocol):
    def stream(self, request: TextGenerationRequest) -> AsyncIterator[str]: ...


class StructuredGenerationPort(Protocol):
    async def generate_structured(
        self, request: StructuredGenerationRequest[StructuredOutput]
    ) -> StructuredGenerationResult[StructuredOutput]: ...
