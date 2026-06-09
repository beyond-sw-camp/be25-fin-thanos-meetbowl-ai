from typing import Any

from google import genai
from google.genai import types
from pydantic import ValidationError

from app.core.errors import (
    ProviderUnavailableError,
    ResponseParseError,
    ResponseValidationError,
)
from app.schemas.minutes import MinutesDraft
from app.schemas.workflow import MinutesGenerationContext


class GeminiLLMProvider:
    def __init__(
        self,
        *,
        api_key: str | None,
        model_name: str,
        temperature: float,
        client: Any | None = None,
    ) -> None:
        self._api_key = api_key
        self._model_name = model_name
        self._temperature = temperature
        self._client = client

    @property
    def model_name(self) -> str:
        return self._model_name

    async def generate_minutes(
        self, *, prompt: str, context: MinutesGenerationContext
    ) -> dict[str, Any]:
        del context
        client = self._get_client()
        try:
            response = await client.aio.models.generate_content(
                model=self._model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=self._temperature,
                    response_mime_type="application/json",
                    response_json_schema=MinutesDraft.model_json_schema(by_alias=True),
                ),
            )
        except ProviderUnavailableError:
            raise
        except Exception as exc:
            raise ProviderUnavailableError() from exc

        if not response.text:
            raise ResponseParseError("Gemini가 빈 응답을 반환했습니다.")
        try:
            draft = MinutesDraft.model_validate_json(response.text)
        except ValidationError as exc:
            raise ResponseValidationError() from exc
        except ValueError as exc:
            raise ResponseParseError() from exc
        return draft.model_dump(mode="json", by_alias=True)

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        if not self._api_key:
            raise ProviderUnavailableError("GEMINI_API_KEY가 설정되지 않았습니다.")
        self._client = genai.Client(api_key=self._api_key)
        return self._client
