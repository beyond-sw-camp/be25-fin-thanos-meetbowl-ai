import hashlib
import math
import re


class FakeEmbeddingProvider:
    """Gemini 없이 RAG 흐름을 검증하기 위한 결정적(deterministic) 임베딩 provider.

    같은 텍스트는 항상 같은 벡터를 만들어 테스트 재현성을 보장한다.
    """

    dimension = 64

    async def embed(self, text: str) -> list[float]:
        """단어를 해시해 고정 차원 벡터에 누적한 뒤 단위 벡터로 정규화한다."""
        vector = [0.0] * self.dimension
        # 단어별 해시값으로 벡터의 한 위치를 정해 빈도를 누적한다(단순 bag-of-words 임베딩).
        for token in re.findall(r"[0-9A-Za-z가-힣]+", text.lower()):
            digest = hashlib.sha256(token.encode()).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimension
            vector[index] += 1.0
        # 코사인 유사도 검색을 위해 크기를 1로 정규화한다(빈 텍스트는 영벡터 그대로 반환).
        magnitude = math.sqrt(sum(value * value for value in vector))
        if magnitude == 0:
            return vector
        return [value / magnitude for value in vector]
