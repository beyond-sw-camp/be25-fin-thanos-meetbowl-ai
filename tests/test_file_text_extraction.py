"""드라이브 파일 텍스트 추출 라우팅 검증.

- 텍스트 PDF: pypdf로 로컬 추출(Gemini 호출 없음)
- 이미지: Gemini 멀티모달
- 스캔 PDF(텍스트 레이어 없음): pypdf가 비면 Gemini로 폴백
- docx/txt: 로컬 추출
"""

import asyncio
import io
from pathlib import Path

from app.core.errors import AiError
from app.pipelines.file_text_extraction import FileTextExtractor
from app.ports.extraction import FileExtractionRequest

FIXTURES = Path(__file__).parent / "fixtures" / "drive"


class FakeGemini:
    def __init__(self, text: str = "GEMINI_TEXT") -> None:
        self._text = text
        self.calls: list[str] = []

    async def extract_text(self, *, content: bytes, mime_type: str) -> str:
        self.calls.append(mime_type)
        return self._text


def _run(fake: FakeGemini, request: FileExtractionRequest):
    return asyncio.run(FileTextExtractor(gemini_extractor=fake).extract(request))


def test_text_pdf_uses_pypdf_without_gemini() -> None:
    data = (FIXTURES / "sample1_weekly_sync_minutes.pdf").read_bytes()
    fake = FakeGemini()
    result = _run(
        fake,
        FileExtractionRequest(content=data, content_type="application/pdf", filename="m.pdf"),
    )
    assert result.extractor == "pypdf"
    assert "회의록" in result.text
    assert fake.calls == []  # 텍스트 PDF는 Gemini를 호출하지 않는다


def test_image_uses_gemini() -> None:
    data = (FIXTURES / "sample3_esg_campaign_sketch.png").read_bytes()
    fake = FakeGemini("ESG CAMPAIGN")
    result = _run(
        fake,
        FileExtractionRequest(content=data, content_type="image/png", filename="i.png"),
    )
    assert result.extractor == "gemini-image"
    assert result.text == "ESG CAMPAIGN"
    assert fake.calls == ["image/png"]


def test_scanned_pdf_falls_back_to_gemini() -> None:
    from pypdf import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buffer = io.BytesIO()
    writer.write(buffer)

    fake = FakeGemini("SCANNED OCR")
    result = _run(
        fake,
        FileExtractionRequest(
            content=buffer.getvalue(), content_type="application/pdf", filename="scan.pdf"
        ),
    )
    assert result.extractor == "gemini-pdf"
    assert result.text == "SCANNED OCR"
    assert fake.calls == ["application/pdf"]


def test_docx_uses_python_docx() -> None:
    from docx import Document

    buffer = io.BytesIO()
    document = Document()
    document.add_paragraph("워드 본문입니다")
    document.save(buffer)

    result = _run(
        FakeGemini(),
        FileExtractionRequest(
            content=buffer.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            filename="a.docx",
        ),
    )
    assert "워드 본문입니다" in result.text
    assert result.extractor == "docx"


def test_txt_is_decoded() -> None:
    result = _run(
        FakeGemini(),
        FileExtractionRequest(
            content="안녕 메모".encode("utf-8"), content_type="text/plain", filename="a.txt"
        ),
    )
    assert result.text == "안녕 메모"
    assert result.extractor == "text"


def test_unsupported_type_raises() -> None:
    raised = False
    try:
        _run(
            FakeGemini(),
            FileExtractionRequest(content=b"PK", content_type="application/zip", filename="a.zip"),
        )
    except AiError:
        raised = True
    assert raised
