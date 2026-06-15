from typing import Any

from google import genai
from google.genai import types

from app.core.errors import ProviderUnavailableError

# 이미지/스캔 PDF에서 원문 텍스트만 그대로 뽑도록 지시한다. 요약·해설을 막아 색인 품질을 지킨다.
_EXTRACTION_PROMPT = (
    "이 문서(이미지 또는 PDF)에 있는 모든 텍스트를 읽어, 보이는 순서대로 그대로 추출해줘. "
    "한국어와 영어를 모두 정확히 인식하고, 설명·요약·번역 없이 추출한 텍스트만 출력해. "
    "텍스트가 전혀 없으면 빈 문자열을 반환해."
)


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
                    _EXTRACTION_PROMPT,
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
