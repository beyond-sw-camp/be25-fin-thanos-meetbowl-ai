from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class FileExtractionRequest:
    """업로드된 파일 1개에서 텍스트를 추출하기 위한 입력."""

    content: bytes
    content_type: str
    filename: str


@dataclass(frozen=True)
class FileExtractionResult:
    """추출된 텍스트와 어떤 방식으로 뽑았는지(추적용)."""

    text: str
    extractor: str


class FileTextExtractorPort(Protocol):
    """드라이브 파일(PDF/이미지/docx/txt)에서 색인용 텍스트를 추출하는 포트."""

    async def extract(self, request: FileExtractionRequest) -> FileExtractionResult: ...
