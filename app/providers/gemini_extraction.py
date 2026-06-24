from typing import Any

from google import genai
from google.genai import types

from app.core.errors import ProviderUnavailableError
from app.prompts.extraction import DOCUMENT_EXTRACTION_PROMPT


class GeminiFileExtractor:
    """Gemini 멀티모달로 이미지/스캔 PDF에서 텍스트를 추출한다(OCR 대체)."""

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

    async def extract_text(self, *, content: bytes, mime_type: str) -> str:
        client = self._get_client()
        try:
            response = await client.aio.models.generate_content(
                model=self._model_name,
                contents=[
                    types.Part.from_bytes(data=content, mime_type=mime_type),
                    DOCUMENT_EXTRACTION_PROMPT,
                ],
            )
        except ProviderUnavailableError:
            raise
        except Exception as exc:
            raise ProviderUnavailableError("Gemini 파일 텍스트 추출에 실패했습니다.") from exc
        return (response.text or "").strip()

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        if not self._api_key:
            raise ProviderUnavailableError("GEMINI_API_KEY가 설정되지 않았습니다.")
        self._client = genai.Client(api_key=self._api_key)
        return self._client
