from typing import Any

from google import genai
from google.genai import types
from pydantic import ValidationError

from app.core.errors import (
    ProviderUnavailableError,
    ResponseParseError,
    ResponseValidationError,
)
from app.ports.generation import (
    StructuredGenerationRequest,
    StructuredGenerationResult,
)


class GeminiStructuredGenerationProvider:
    def __init__(
        self,
        *,
        api_key: str | None,
        model_name: str,
        default_temperature: float,
        client: Any | None = None,
    ) -> None:
        self._api_key = api_key
        self._model_name = model_name
        self._default_temperature = default_temperature
        self._client = client

    async def generate_structured(
        self, request: StructuredGenerationRequest
    ) -> StructuredGenerationResult:
        client = self._get_client()
        try:
            response = await client.aio.models.generate_content(
                model=self._model_name,
                contents=request.prompt,
                config=types.GenerateContentConfig(
                    temperature=(
                        request.temperature
                        if request.temperature is not None
                        else self._default_temperature
                    ),
                    response_mime_type="application/json",
                    response_json_schema=request.response_schema.model_json_schema(
                        by_alias=True
                    ),
                ),
            )
        except ProviderUnavailableError:
            raise
        except Exception as exc:
            raise ProviderUnavailableError() from exc

        if not response.text:
            raise ResponseParseError("Gemini가 빈 응답을 반환했습니다.")
        try:
            output = request.response_schema.model_validate_json(response.text)
        except ValidationError as exc:
            raise ResponseValidationError() from exc
        except ValueError as exc:
            raise ResponseParseError() from exc
        return StructuredGenerationResult(output=output, model_name=self._model_name)

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        if not self._api_key:
            raise ProviderUnavailableError("GEMINI_API_KEY가 설정되지 않았습니다.")
        self._client = genai.Client(api_key=self._api_key)
        return self._client
