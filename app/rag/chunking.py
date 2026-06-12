import re

DEFAULT_MAX_CHARS = 1200
DEFAULT_OVERLAP_CHARS = 150


def chunk_text(
    text: str,
    *,
    max_chars: int = DEFAULT_MAX_CHARS,
    overlap_chars: int = DEFAULT_OVERLAP_CHARS,
) -> list[str]:
    """문서 본문을 검색·임베딩 단위(청크)로 분할한다.

    문단 경계를 우선 보존하고, 한 문단이 `max_chars`를 넘으면 글자 수 윈도우로
    나눈다. 인접 청크 사이에는 `overlap_chars` 만큼 겹침을 둬서 경계에서 잘린
    문맥이 검색에서 손실되는 것을 줄인다. 대용량 색인에서 청크 크기는 검색 정밀도와
    저장 비용의 균형점이므로 설정으로 조정한다.
    """
    cleaned = text.strip()
    if not cleaned:
        return []
    if overlap_chars >= max_chars:
        overlap_chars = max_chars // 4

    units = _split_into_units(cleaned, max_chars=max_chars, overlap_chars=overlap_chars)

    chunks: list[str] = []
    current = ""
    for unit in units:
        candidate = f"{current}\n\n{unit}".strip() if current else unit
        # 현재 청크에 다음 단위를 더하면 한계를 넘으면, 현재 청크를 확정하고
        # 직전 청크 끝부분을 overlap으로 이어 새 청크를 시작한다.
        if current and len(candidate) > max_chars:
            chunks.append(current)
            tail = _tail(current, overlap_chars)
            current = f"{tail}\n\n{unit}".strip() if tail else unit
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


def _split_into_units(
    text: str, *, max_chars: int, overlap_chars: int
) -> list[str]:
    """본문을 문단으로 1차 분할하고, 너무 긴 문단은 글자 수 윈도우로 강제 분할한다."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    units: list[str] = []
    for paragraph in paragraphs:
        if len(paragraph) <= max_chars:
            units.append(paragraph)
        else:
            units.extend(
                _split_by_window(paragraph, max_chars=max_chars, overlap_chars=overlap_chars)
            )
    return units


def _split_by_window(text: str, *, max_chars: int, overlap_chars: int) -> list[str]:
    """긴 텍스트를 overlap을 둔 고정 글자 수 윈도우로 나눈다."""
    step = max(1, max_chars - overlap_chars)
    windows: list[str] = []
    start = 0
    while start < len(text):
        windows.append(text[start : start + max_chars])
        start += step
    return windows


def _tail(text: str, overlap_chars: int) -> str:
    """청크 끝에서 overlap 길이만큼 잘라 다음 청크 앞에 붙일 문맥을 만든다."""
    if overlap_chars <= 0:
        return ""
    return text[-overlap_chars:]
