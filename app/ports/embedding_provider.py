from typing import Protocol


class EmbeddingProvider(Protocol):
    """텍스트를 벡터로 변환하는 임베딩 provider 계약(실제 Gemini / 테스트용 Fake 공통)."""

    async def embed(self, text: str) -> list[float]:
        """주어진 텍스트를 임베딩 벡터로 변환한다."""
        ...
