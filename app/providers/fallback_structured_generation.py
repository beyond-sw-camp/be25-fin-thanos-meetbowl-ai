import logging

from app.core.errors import ProviderUnavailableError
from app.ports.generation import (
    StructuredGenerationPort,
    StructuredGenerationRequest,
    StructuredGenerationResult,
)

logger = logging.getLogger("uvicorn.error")


class FallbackStructuredGenerationProvider:
    """기본 구조화 생성이 과부하/불가일 때 대체 provider로 넘기는 래퍼.

    챗봇 답변 생성(single_pass)을 Gemini 503에서 OpenAI로 폴백시켜, agentic의 FallbackModel과
    동일한 수준의 내구성을 구조화 생성 경로에도 부여한다.
    """

    def __init__(
        self,
        *,
        primary: StructuredGenerationPort,
        fallback: StructuredGenerationPort,
    ) -> None:
        self._primary = primary
        self._fallback = fallback

    async def generate_structured(
        self, request: StructuredGenerationRequest
    ) -> StructuredGenerationResult:
        try:
            return await self._primary.generate_structured(request)
        except ProviderUnavailableError as exc:
            logger.warning(
                "primary structured generation unavailable, falling back: %s", exc
            )
            return await self._fallback.generate_structured(request)
