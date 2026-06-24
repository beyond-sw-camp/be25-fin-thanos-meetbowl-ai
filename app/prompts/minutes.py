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
출력은 반드시 자연스러운 한국어 서술형 문장으로만 작성한다.
원문 발화를 따옴표로 직접 인용하거나 잘린 말투를 그대로 복사하지 않는다.
회의록은 회의 내용을 정리하는 문서다. 링크 공유, 접속 확인, 들림/안 들림, 자막/마이크 점검,
반복 감탄사, 원인 탐색 중간 멘트처럼 운영성 잡음은 안건이나 결정사항으로 승격하지 않는다.
실질적인 논의나 합의가 부족하면 요약만 짧게 작성하고 안건별 논의·결정사항·후속 조치는 빈 배열로 반환한다.
안건별 논의는 발화 모음이 아니라, 실제로 논의된 주제를 정제한 설명문으로 작성한다.
결정사항과 후속 조치가 확인되지 않으면 빈 배열을 반환한다.
후속 조치 담당자가 명확하지 않으면 assigneeName을 null로 반환한다.

회의 제목: {context.title}
참여자:
{participants}

회의 원문:
{context.raw_transcript}
"""
