import io

from app.core.errors import AiError
from app.ports.extraction import (
    FileExtractionRequest,
    FileExtractionResult,
    FileTextExtractorPort,
)
from app.providers.gemini_extraction import GeminiFileExtractor

# pypdf 추출 결과가 이보다 짧으면 텍스트 레이어가 없는 스캔/이미지 PDF로 보고 Gemini로 넘긴다.
_MIN_PDF_TEXT_CHARS = 30


class FileTextExtractor(FileTextExtractorPort):
    """content_type에 따라 추출기를 고른다.

    - 텍스트 PDF: pypdf(빠르고 무료) → 텍스트가 거의 없으면 스캔본으로 보고 Gemini로 대체
    - 이미지: Gemini 멀티모달(OCR 대체)
    - docx: python-docx
    - txt/markdown: 디코드
    """

    def __init__(self, *, gemini_extractor: GeminiFileExtractor) -> None:
        self._gemini = gemini_extractor

    async def extract(self, request: FileExtractionRequest) -> FileExtractionResult:
        content_type = (request.content_type or "").split(";")[0].strip().lower()
        name = request.filename.lower()

        if content_type.startswith("image/"):
            text = await self._gemini.extract_text(
                content=request.content, mime_type=content_type
            )
            return FileExtractionResult(text=text, extractor="gemini-image")

        if content_type == "application/pdf" or name.endswith(".pdf"):
            return await self._extract_pdf(request)

        if (
            content_type
            == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            or name.endswith(".docx")
        ):
            return FileExtractionResult(text=self._extract_docx(request.content), extractor="docx")

        if content_type.startswith("text/") or name.endswith((".txt", ".md", ".csv")):
            return FileExtractionResult(text=self._decode_text(request.content), extractor="text")

        raise AiError(
            "AI_INVALID_EVENT",
            f"지원하지 않는 파일 형식입니다: {content_type or request.filename}",
            status_code=400,
        )

    async def _extract_pdf(self, request: FileExtractionRequest) -> FileExtractionResult:
        from pypdf import PdfReader

        try:
            reader = PdfReader(io.BytesIO(request.content))
            text = "\n".join((page.extract_text() or "") for page in reader.pages).strip()
        except Exception:
            text = ""

        # 텍스트 레이어가 없는 스캔 PDF면 PDF 바이트를 그대로 Gemini에 보내 OCR한다.
        if len(text) >= _MIN_PDF_TEXT_CHARS:
            return FileExtractionResult(text=text, extractor="pypdf")
        gemini_text = await self._gemini.extract_text(
            content=request.content, mime_type="application/pdf"
        )
        return FileExtractionResult(text=gemini_text, extractor="gemini-pdf")

    def _extract_docx(self, content: bytes) -> str:
        from docx import Document

        document = Document(io.BytesIO(content))
        return "\n".join(p.text for p in document.paragraphs if p.text).strip()

    def _decode_text(self, content: bytes) -> str:
        for encoding in ("utf-8", "cp949", "euc-kr"):
            try:
                return content.decode(encoding).strip()
            except UnicodeDecodeError:
                continue
        return content.decode("utf-8", errors="replace").strip()
