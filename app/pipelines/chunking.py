from app.schemas.indexing import DocumentChunk


def split_document_into_chunks(
    *, title: str, content: str, max_chars: int, overlap_chars: int
) -> list[DocumentChunk]:
    # 초기 색인 전략은 문단 경계를 우선 보존한다.
    # 같은 회의록을 다시 색인해도 동일한 입력이면 동일한 chunk 순서가 나오도록
    # 결정적인 규칙만 사용한다.
    normalized_blocks = [block.strip() for block in content.split("\n\n") if block.strip()]
    if not normalized_blocks:
        return []

    chunks: list[str] = []
    current = ""
    for block in normalized_blocks:
        candidate = block if not current else f"{current}\n\n{block}"
        if len(candidate) <= max_chars:
            current = candidate
            continue
        if current:
            chunks.append(current)
        if len(block) <= max_chars:
            current = block
            continue
        chunks.extend(_split_long_block(block, max_chars=max_chars, overlap_chars=overlap_chars))
        current = ""

    if current:
        chunks.append(current)

    return [
        DocumentChunk(
            chunk_index=index,
            content=chunk,
            embedding_text=f"{title}\n\n{chunk}",
        )
        for index, chunk in enumerate(chunks)
    ]


def _split_long_block(block: str, *, max_chars: int, overlap_chars: int) -> list[str]:
    if max_chars <= 0:
        raise ValueError("max_chars must be positive")
    if overlap_chars < 0:
        raise ValueError("overlap_chars must not be negative")
    if overlap_chars >= max_chars:
        raise ValueError("overlap_chars must be smaller than max_chars")

    if _is_markdown_table(block):
        return _split_markdown_table(block, max_chars=max_chars)

    # 긴 단일 문단은 겹침 구간을 남겨 다음 chunk가 앞 문맥을 일부 이어받게 한다.
    return _split_plain_window(block, max_chars=max_chars, overlap_chars=overlap_chars)


def _is_markdown_table(block: str) -> bool:
    """Markdown 표 블록인지 보수적으로 판정한다.

    PDF 추출 후 표를 Markdown으로 정규화한 경우 행/열 매핑을 보존하기 위해
    일반 글자 수 윈도우 분할 대신 행 단위 분할을 적용한다.
    """
    lines = [line.strip() for line in block.splitlines() if line.strip()]
    if len(lines) < 2:
        return False
    table_like_lines = [line for line in lines if line.startswith("|") and line.endswith("|")]
    if len(table_like_lines) != len(lines):
        return False
    return any(_is_markdown_separator(line) for line in lines[:3])


def _is_markdown_separator(line: str) -> bool:
    cells = [cell.strip() for cell in line.strip("|").split("|")]
    return bool(cells) and all(
        cell and set(cell) <= {"-", ":"} and "-" in cell for cell in cells
    )


def _split_markdown_table(block: str, *, max_chars: int) -> list[str]:
    """긴 Markdown 표를 행 단위로 나누되 각 조각에 헤더를 반복한다."""
    lines = [line.strip() for line in block.splitlines() if line.strip()]
    separator_index = next(
        (index for index, line in enumerate(lines[:3]) if _is_markdown_separator(line)),
        1,
    )
    header = lines[: separator_index + 1]
    rows = lines[separator_index + 1 :]

    # 헤더 자체가 너무 길면 보존할 수 있는 구조가 없으므로 기존 윈도우 분할로 되돌린다.
    header_text = "\n".join(header)
    if len(header_text) >= max_chars:
        return _split_plain_window(block, max_chars=max_chars, overlap_chars=0)

    chunks: list[str] = []
    current = header.copy()
    for row in rows:
        candidate = "\n".join([*current, row])
        if len(candidate) <= max_chars:
            current.append(row)
            continue
        if len(current) > len(header):
            chunks.append("\n".join(current))
            current = [*header, row]
            if len("\n".join(current)) > max_chars:
                chunks.extend(_split_plain_window(row, max_chars=max_chars, overlap_chars=0))
                current = header.copy()
            continue
        chunks.extend(_split_plain_window(row, max_chars=max_chars, overlap_chars=0))
        current = header.copy()

    if len(current) > len(header):
        chunks.append("\n".join(current))
    elif not chunks:
        chunks.append(header_text)
    return chunks


def _split_plain_window(text: str, *, max_chars: int, overlap_chars: int) -> list[str]:
    chunks: list[str] = []
    start = 0
    text_length = len(text)
    while start < text_length:
        end = min(start + max_chars, text_length)
        window = text[start:end].strip()
        if window:
            chunks.append(window)
        if end >= text_length:
            break
        start = max(end - overlap_chars, start + 1)
    return chunks
