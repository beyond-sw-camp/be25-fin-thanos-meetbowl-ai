from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class VectorPoint:
    point_id: str
    vector: list[float]
    payload: dict[str, Any]


@dataclass(frozen=True)
class ReplaceDocumentRequest:
    document_id: str
    vector_size: int
    points: list[VectorPoint]


class VectorStorePort(Protocol):
    async def replace_document(self, request: ReplaceDocumentRequest) -> None: ...
