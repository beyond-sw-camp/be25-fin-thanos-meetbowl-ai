import hashlib
import re
from typing import Any

_TOKEN_PATTERN = re.compile(r"[0-9A-Za-z가-힣]+")


class SparseEncoder:
    """텍스트를 BM25용 sparse 벡터(토큰 빈도)로 변환한다.

    토큰을 32bit 정수 인덱스로 해시하고 등장 빈도(term frequency)를 값으로 둔다.
    IDF 가중치는 Qdrant sparse 인덱스의 `modifier: idf`가 질의 시점에 적용하므로
    여기서는 raw 빈도만 만든다. 결정적 변환이라 외부 모델 없이 재현 가능하다.
    """

    def encode(self, text: str) -> dict[str, list[Any]]:
        """텍스트를 Qdrant sparse 벡터 형식 {indices, values}로 변환한다."""
        counts: dict[int, float] = {}
        for token in _TOKEN_PATTERN.findall(text.lower()):
            index = int.from_bytes(hashlib.sha256(token.encode()).digest()[:4], "big")
            counts[index] = counts.get(index, 0.0) + 1.0
        return {
            "indices": list(counts.keys()),
            "values": list(counts.values()),
        }
