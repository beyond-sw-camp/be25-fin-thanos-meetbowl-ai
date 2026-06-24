import re

from app.schemas.minutes import TranscriptSegment


def normalize_raw_transcript(raw_transcript: str) -> str:
    """Keep the generation pipeline independent from the upstream transcript shape.

    If the upstream contract later becomes a list of utterances, an adapter should
    sort and join that list before calling this normalization boundary.
    """
    normalized_lines = [" ".join(line.split()) for line in raw_transcript.splitlines()]
    filtered_lines = [
        line
        for line in normalized_lines
        if line
        and "http://" not in line
        and "https://" not in line
        and "www." not in line
        and line not in {"공유 링크 복사", "공유 링크", "링크 복사"}
    ]
    return "\n".join(filtered_lines)


def transcript_to_segments(raw_transcript: str) -> list[TranscriptSegment]:
    normalized = normalize_raw_transcript(raw_transcript)
    return [
        TranscriptSegment(sequence=index, source_text=line)
        for index, line in enumerate(normalized.splitlines(), start=1)
        if line
    ]


def mark_suspicious_segments(segments: list[TranscriptSegment]) -> list[TranscriptSegment]:
    if not segments:
        return []
    dominant_scripts = [_dominant_script(segment.source_text) for segment in segments]
    marked: list[TranscriptSegment] = []
    for index, segment in enumerate(segments):
        suspicious = _is_suspicious_outlier(
            segment=segment,
            index=index,
            segments=segments,
            dominant_scripts=dominant_scripts,
        )
        marked.append(segment.model_copy(update={"suspicious": suspicious}))
    return marked


def _is_suspicious_outlier(
    *,
    segment: TranscriptSegment,
    index: int,
    segments: list[TranscriptSegment],
    dominant_scripts: list[str],
) -> bool:
    script = dominant_scripts[index]
    if script in {"hangul", "latin", "mixed", "other"}:
        return False
    text = segment.source_text.strip()
    if len(text) > 24:
        return False
    if len(_letters_only(text)) < 2:
        return False
    same_script_neighbors = 0
    for neighbor_index in range(max(0, index - 2), min(len(segments), index + 3)):
        if neighbor_index == index:
            continue
        if dominant_scripts[neighbor_index] == script:
            same_script_neighbors += 1
    if same_script_neighbors >= 1:
        return False
    nearby_mainstream = 0
    for neighbor_index in range(max(0, index - 2), min(len(segments), index + 3)):
        if neighbor_index == index:
            continue
        if dominant_scripts[neighbor_index] in {"hangul", "latin", "mixed"}:
            nearby_mainstream += 1
    return nearby_mainstream >= 1


def _dominant_script(text: str) -> str:
    counts = {
        "hangul": len(re.findall(r"[가-힣]", text)),
        "latin": len(re.findall(r"[A-Za-z]", text)),
        "hiragana_katakana": len(re.findall(r"[\u3040-\u30ff]", text)),
        "han": len(re.findall(r"[\u4e00-\u9fff]", text)),
    }
    best_script = max(counts, key=counts.get)
    best_count = counts[best_script]
    if best_count == 0:
        return "other"
    active_scripts = sum(1 for count in counts.values() if count > 0)
    if active_scripts >= 2 and counts["hangul"] > 0:
        return "mixed"
    return best_script


def _letters_only(text: str) -> str:
    return "".join(char for char in text if char.isalpha())
