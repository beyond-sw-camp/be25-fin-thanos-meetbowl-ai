from typing import Protocol

from app.schemas.workflow import MinutesGenerationCommand, MinutesGenerationContext


class MinutesContextLoader(Protocol):
    async def load(self, command: MinutesGenerationCommand) -> MinutesGenerationContext: ...
