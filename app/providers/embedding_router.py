from collections.abc import Mapping

from app.core.errors import ModelProfileNotConfiguredError
from app.ports.embedding import EmbeddingPort, EmbeddingRequest, EmbeddingResult


class ProfileRoutingEmbeddingProvider:
    def __init__(self, routes: Mapping[str, EmbeddingPort]) -> None:
        self._routes = dict(routes)

    async def embed(self, request: EmbeddingRequest) -> EmbeddingResult:
        provider = self._routes.get(request.model_profile)
        if provider is None:
            raise ModelProfileNotConfiguredError(request.model_profile)
        return await provider.embed(request)
