"""본문 청킹(문단 보존 + 길이 분할 + overlap) 단위 테스트."""

from app.rag.chunking import chunk_text


def test_blank_text_produces_no_chunks() -> None:
    assert chunk_text("   \n\n  ") == []


def test_short_text_stays_as_single_chunk() -> None:
    chunks = chunk_text("금요일 배포로 결정했습니다.", max_chars=1200)

    assert chunks == ["금요일 배포로 결정했습니다."]


def test_long_paragraph_is_split_into_overlapping_windows() -> None:
    text = "가나다라마바사" * 400  # 2800자, max_chars를 크게 초과
    max_chars = 1000
    overlap_chars = 100

    chunks = chunk_text(text, max_chars=max_chars, overlap_chars=overlap_chars)

    assert len(chunks) >= 3
    # 각 청크는 한계 + overlap 여유 안에 들어와야 한다.
    for chunk in chunks:
        assert 0 < len(chunk) <= max_chars + overlap_chars + 4
    # 인접 청크는 overlap 만큼 문맥을 공유한다.
    assert chunks[0][-overlap_chars:] in chunks[1]


def test_multiple_paragraphs_split_on_paragraph_boundary() -> None:
    first = "회의 안건은 배포 일정입니다. " * 30
    second = "예산 검토는 다음 주에 진행합니다. " * 30
    text = f"{first.strip()}\n\n{second.strip()}"

    chunks = chunk_text(text, max_chars=900, overlap_chars=100)

    assert len(chunks) >= 2
    assert "배포 일정" in chunks[0]
    assert "예산 검토" in chunks[-1]
