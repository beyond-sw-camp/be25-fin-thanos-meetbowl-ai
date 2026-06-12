from app.ports.embedding import EmbeddingRequest, EmbeddingResult


class FakeEmbeddingProvider:
    def __init__(self, model_name: str, dimensions: int = 4) -> None:
        self._model_name = model_name
        self._dimensions = dimensions

    async def embed(self, request: EmbeddingRequest) -> EmbeddingResult:
        embeddings = [
            [float((index + offset) % 7) for offset in range(self._dimensions)]
            for index, _ in enumerate(request.texts)
        ]
        return EmbeddingResult(
            embeddings=embeddings,
            model_name=self._model_name,
            dimensions=self._dimensions,
        )
