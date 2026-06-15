import httpx

from app.core.errors import DocumentIndexFailedError, ProviderUnavailableError
from app.ports.embedding import EmbeddingRequest, EmbeddingResult


class OpenAIEmbeddingProvider:
    def __init__(
        self,
        *,
        api_key: str | None,
        base_url: str,
        model_name: str,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model_name = model_name
        self._client = client or httpx.AsyncClient(timeout=30.0)
        self._owns_client = client is None

    async def embed(self, request: EmbeddingRequest) -> EmbeddingResult:
        if not self._api_key:
            raise ProviderUnavailableError("OPENAI_API_KEY가 설정되지 않았습니다.")

        try:
            response = await self._client.post(
                f"{self._base_url}/embeddings",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "input": request.texts,
                    "model": self._model_name,
                    "encoding_format": "float",
                },
            )
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError(
                "OpenAI 임베딩 Provider를 사용할 수 없습니다."
            ) from exc

        if response.status_code >= 500 or response.status_code == 429:
            raise ProviderUnavailableError("OpenAI 임베딩 API가 일시적으로 실패했습니다.")
        if response.status_code >= 400:
            raise DocumentIndexFailedError(
                f"OpenAI 임베딩 요청이 실패했습니다. status={response.status_code}",
                retryable=False,
            )

        payload = response.json()
        items = payload.get("data")
        if not isinstance(items, list) or not items:
            raise DocumentIndexFailedError(
                "OpenAI 임베딩 응답에 data가 없습니다.",
                retryable=False,
            )

        embeddings = []
        for item in items:
            vector = item.get("embedding")
            if not isinstance(vector, list) or not vector:
                raise DocumentIndexFailedError(
                    "OpenAI 임베딩 응답 형식이 올바르지 않습니다.",
                    retryable=False,
                )
            embeddings.append([float(value) for value in vector])

        if len(embeddings) != len(request.texts):
            raise DocumentIndexFailedError("임베딩 응답 개수가 요청과 다릅니다.")

        model_name = payload.get("model", self._model_name)
        return EmbeddingResult(
            embeddings=embeddings,
            model_name=model_name,
            dimensions=len(embeddings[0]),
        )

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()
