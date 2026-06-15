from typing import Any

from google import genai
from google.genai import types

from app.core.errors import DocumentIndexFailedError, ProviderUnavailableError
from app.ports.embedding import EmbeddingRequest, EmbeddingResult


class GeminiEmbeddingProvider:
    def __init__(
        self,
        *,
        api_key: str | None,
        model_name: str,
        client: Any | None = None,
    ) -> None:
        self._api_key = api_key
        self._model_name = model_name
        self._client = client

    async def embed(self, request: EmbeddingRequest) -> EmbeddingResult:
        client = self._get_client()
        try:
            response = await client.aio.models.embed_content(
                model=self._model_name,
                contents=request.texts,
                config=types.EmbedContentConfig(task_type="RETRIEVAL_DOCUMENT"),
            )
        except ProviderUnavailableError:
            raise
        except Exception as exc:
            raise ProviderUnavailableError(
                "문서 임베딩 Provider를 사용할 수 없습니다."
            ) from exc

        embeddings = []
        for item in getattr(response, "embeddings", []) or []:
            values = getattr(item, "values", None)
            if not values:
                raise DocumentIndexFailedError(
                    "Gemini 임베딩 응답에 벡터 값이 없습니다.", retryable=False
                )
            embeddings.append([float(value) for value in values])
        if not embeddings:
            raise DocumentIndexFailedError(
                "Gemini가 빈 임베딩 응답을 반환했습니다.", retryable=False
            )
        if len(embeddings) != len(request.texts):
            raise DocumentIndexFailedError("임베딩 응답 개수가 요청과 다릅니다.")
        return EmbeddingResult(
            embeddings=embeddings,
            model_name=self._model_name,
            dimensions=len(embeddings[0]),
        )

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        if not self._api_key:
            raise ProviderUnavailableError("GEMINI_API_KEY가 설정되지 않았습니다.")
        self._client = genai.Client(api_key=self._api_key)
        return self._client
