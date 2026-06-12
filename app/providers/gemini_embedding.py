from typing import Any

from google import genai

from app.core.errors import ProviderUnavailableError


class GeminiEmbeddingProvider:
    """실제 Gemini API로 텍스트 임베딩을 생성하는 운영용 provider."""

    def __init__(self, *, api_key: str | None, model_name: str, client: Any | None = None) -> None:
        self._api_key = api_key
        self._model_name = model_name
        self._client = client

    async def embed(self, text: str) -> list[float]:
        """Gemini embedding 모델을 호출해 임베딩 벡터를 반환한다."""
        try:
            response = await self._get_client().aio.models.embed_content(
                model=self._model_name,
                contents=text,
            )
            values = response.embeddings[0].values
            if not values:
                raise ProviderUnavailableError("Gemini가 빈 임베딩을 반환했습니다.")
            return list(values)
        except ProviderUnavailableError:
            raise
        except Exception as exc:
            raise ProviderUnavailableError("문서 임베딩 생성에 실패했습니다.") from exc

    def _get_client(self) -> Any:
        """Gemini client를 최초 사용 시점에 한 번만 생성(lazy)해 재사용한다."""
        if self._client is not None:
            return self._client
        if not self._api_key:
            raise ProviderUnavailableError("GEMINI_API_KEY가 설정되지 않았습니다.")
        self._client = genai.Client(api_key=self._api_key)
        return self._client
