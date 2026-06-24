from collections.abc import Mapping

from app.core.errors import ModelProfileNotConfiguredError
from app.ports.generation import (
    StructuredGenerationPort,
    StructuredGenerationRequest,
    StructuredGenerationResult,
    StructuredOutput,
)


class ProfileRoutingStructuredGenerationProvider:
    def __init__(self, routes: Mapping[str, StructuredGenerationPort]) -> None:
        self._routes = dict(routes)

    async def generate_structured(
        self, request: StructuredGenerationRequest[StructuredOutput]
    ) -> StructuredGenerationResult[StructuredOutput]:
        provider = self._routes.get(request.model_profile)
        if provider is None:
            raise ModelProfileNotConfiguredError(request.model_profile)
        return await provider.generate_structured(request)
