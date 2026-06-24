from app.schemas.minutes import TranscriptSegment
from app.schemas.workflow import MinutesGenerationContext


def build_minutes_evidence_prompt(
    *,
    prompt_version: str,
    context: MinutesGenerationContext,
    segments: list[TranscriptSegment],
) -> str:
    participants = "\n".join(
        f"- {participant.name}"
        + (f" ({participant.department})" if participant.department else "")
        for participant in context.participants
    )
    transcript_block = "\n".join(
        (
            f"{segment.sequence}. "
            f"{'[SUSPICIOUS] ' if segment.suspicious else ''}"
            f"[{segment.language or 'UNKNOWN'}"
            f"{f' {segment.started_at_ms}-{segment.ended_at_ms}ms' if segment.started_at_ms is not None and segment.ended_at_ms is not None else ''}] "
            f"{segment.source_text}"
        )
        for segment in segments
    )
    return f"""[{prompt_version}:evidence]
다음 회의 transcript segment만 근거로 회의록 초안의 근거(evidence)만 추출한다.
출력은 schema에 맞는 JSON만 반환한다.
추측하거나 원문에 없는 결정, 안건, 후속 조치를 추가하지 않는다.
요약과 discussionPoints는 자연스러운 한국어 서술형 문장으로 작성한다.
발화를 그대로 길게 복사하지 말고, 여러 segment를 묶어 핵심만 정리한다.
summary는 2~4문장 범위에서 회의 목적, 주요 논의, 결정/후속조치를 압축해 작성한다.
명시적인 합의가 없으면 decisions는 빈 배열로 반환한다.
담당자나 기한이 명확하지 않으면 action item의 assigneeName, dueDate는 null로 반환한다.
실질적인 논의가 부족하면 agendaItems, decisions, actionItems를 비울 수 있다.
각 agenda item, decision, action item에는 반드시 근거가 된 sourceSequences를 넣는다.
sourceSequences에는 아래 transcript 번호만 넣고, 존재하지 않는 번호는 넣지 않는다.
agenda item은 최소 2개 이상의 관련 segment가 있을 때만 만드는 것을 우선한다. 단, 단일 segment라도 명시적 결정이나 명확한 후속 조치가 있으면 허용한다.
discussionPoints는 agenda item당 최대 3개만 넣고, 중복 표현을 반복하지 않는다.
decision과 action item은 각각 sourceSequences가 가리키는 segment를 보고도 바로 납득 가능한 문장만 남긴다.
`[SUSPICIOUS]`가 붙은 segment는 STT 오인식 가능성이 있는 고립된 조각이므로, 다른 정상 segment가 함께 뒷받침하지 않으면 안건/결정/후속조치 근거로 사용하지 않는다.

회의 제목: {context.title}
참여자:
{participants}

Transcript Segments:
{transcript_block}
"""
