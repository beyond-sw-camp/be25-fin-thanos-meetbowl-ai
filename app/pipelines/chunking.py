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

    chunks: list[str] = []
    start = 0
    block_length = len(block)
    while start < block_length:
        end = min(start + max_chars, block_length)
        window = block[start:end].strip()
        if window:
            chunks.append(window)
        if end >= block_length:
            break
        # 긴 단일 문단은 겹침 구간을 남겨 다음 chunk가 앞 문맥을 일부 이어받게 한다.
        start = max(end - overlap_chars, start + 1)
    return chunks
