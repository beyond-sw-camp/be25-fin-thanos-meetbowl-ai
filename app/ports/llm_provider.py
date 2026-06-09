from typing import Any, Protocol

from app.schemas.workflow import MinutesGenerationContext


class LLMProvider(Protocol):
    @property
    def model_name(self) -> str: ...

    async def generate_minutes(
        self, *, prompt: str, context: MinutesGenerationContext
    ) -> dict[str, Any]: ...
