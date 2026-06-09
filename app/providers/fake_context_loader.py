from datetime import datetime, timedelta, timezone
from uuid import NAMESPACE_URL, uuid5

from app.core.errors import ContextNotFoundError
from app.schemas.minutes import Participant
from app.schemas.workflow import MinutesGenerationCommand, MinutesGenerationContext


class FakeMinutesContextLoader:
    async def load(self, command: MinutesGenerationCommand) -> MinutesGenerationContext:
        if not command.meeting_id:
            raise ContextNotFoundError()

        host_user_id = command.host_user_id or uuid5(
            NAMESPACE_URL, f"{command.meeting_id}:host"
        )
        started_at = command.started_at or datetime(2026, 6, 1, 0, 0, tzinfo=timezone.utc)
        ended_at = command.ended_at or started_at + timedelta(hours=1)
        return MinutesGenerationContext(
            meeting_id=command.meeting_id,
            organization_id=command.organization_id,
            host_user_id=host_user_id,
            reviewer_user_id=command.reviewer_user_id,
            title=command.title or "회의록 생성 테스트 회의",
            started_at=started_at,
            ended_at=ended_at,
            participants=command.participants
            if command.participants is not None
            else [
                Participant(user_id=host_user_id, name="홍길동", department="기획팀"),
                Participant(
                    user_id=command.reviewer_user_id, name="김검토", department="개발팀"
                ),
            ],
            # 실제 BE context adapter가 생기기 전까지 Rabbit 경로에 결정적인 긴 원문을 제공한다.
            raw_transcript=command.raw_transcript
            if command.raw_transcript is not None
            else "오늘 안건은 배포 일정입니다.\n금요일까지 배포 준비를 완료하겠습니다.",
        )
