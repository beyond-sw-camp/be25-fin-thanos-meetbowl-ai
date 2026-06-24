from app.schemas.workflow import MinutesGenerationContext


def build_minutes_prompt(*, prompt_version: str, context: MinutesGenerationContext) -> str:
    participants = "\n".join(
        f"- {participant.name}"
        + (f" ({participant.department})" if participant.department else "")
        for participant in context.participants
    )
    return f"""[{prompt_version}]
다음 회의 원문만 근거로 검토 전 회의록 초안을 작성한다.
추측하거나 원문에 없는 결정을 추가하지 않는다.
결정사항과 후속 조치가 확인되지 않으면 빈 배열을 반환한다.
후속 조치 담당자가 명확하지 않으면 assigneeName을 null로 반환한다.

회의 제목: {context.title}
참여자:
{participants}

회의 원문:
{context.raw_transcript}
"""
