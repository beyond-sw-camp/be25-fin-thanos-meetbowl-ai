from typing import Any

from openai import AsyncOpenAI

from app.core.errors import ProviderUnavailableError, ResponseParseError
from app.ports.generation import (
    StructuredGenerationRequest,
    StructuredGenerationResult,
)


class OpenAIStructuredGenerationProvider:
    """OpenAI structured outputs로 구조화 생성을 수행한다(Gemini 과부하 시 대체 경로).

    `GeminiStructuredGenerationProvider`와 동일 계약을 따른다: prompt + response_schema를 받아
    스키마로 검증된 객체를 돌려준다. 질의 확장처럼 Gemini 503에 취약한 단계를 안정화하는 용도다.
    """

    def __init__(
        self,
        *,
        api_key: str | None,
        base_url: str,
        model_name: str,
        default_temperature: float,
        client: Any | None = None,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url
        self._model_name = model_name
        self._default_temperature = default_temperature
        self._client = client

    async def generate_structured(
        self, request: StructuredGenerationRequest
    ) -> StructuredGenerationResult:
        client = self._get_client()
        try:
            response = await client.chat.completions.parse(
                model=self._model_name,
                messages=[{"role": "user", "content": request.prompt}],
                temperature=(
                    request.temperature
                    if request.temperature is not None
                    else self._default_temperature
                ),
                response_format=request.response_schema,
            )
        except Exception as exc:
            raise ProviderUnavailableError() from exc

        parsed = response.choices[0].message.parsed
        if parsed is None:
            raise ResponseParseError("OpenAI가 빈 구조화 응답을 반환했습니다.")
        return StructuredGenerationResult(output=parsed, model_name=self._model_name)

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        if not self._api_key:
            raise ProviderUnavailableError("OPENAI_API_KEY가 설정되지 않았습니다.")
        self._client = AsyncOpenAI(api_key=self._api_key, base_url=self._base_url)
        return self._client
