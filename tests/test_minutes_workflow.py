import asyncio
from datetime import datetime, timezone
from uuid import uuid4

from app.providers.fake_generation import FakeStructuredGenerationProvider
from app.providers.http_minutes_context_loader import HttpMinutesContextLoader
from app.workflows.minutes_generation import MinutesGenerationWorkflow
from app.schemas.workflow import MinutesGenerationCommand


def test_minutes_workflow_builds_draft_from_evidence() -> None:
    meeting_id = uuid4()
    organization_id = uuid4()
    host_user_id = uuid4()
    reviewer_user_id = uuid4()

    async def run():
        workflow = MinutesGenerationWorkflow(
            context_loader=HttpMinutesContextLoader(
                base_url="http://be",
                internal_token="internal-token",
                timeout_seconds=1.0,
            ),
            structured_generation_port=FakeStructuredGenerationProvider("fake-minutes-model"),
            model_profile="minutes-summary",
            prompt_version="minutes-v1",
        )
        return await workflow.execute(
            MinutesGenerationCommand(
                meeting_id=meeting_id,
                organization_id=organization_id,
                host_user_id=host_user_id,
                reviewer_user_id=reviewer_user_id,
                title="배포 일정 조율 회의",
                started_at=datetime(2026, 6, 24, 0, tzinfo=timezone.utc),
                ended_at=datetime(2026, 6, 24, 1, tzinfo=timezone.utc),
                participants=[],
                raw_transcript=(
                    "금요일 오후 배포로 진행하는 게 어떨까요?\n"
                    "QA 확인은 목요일까지 마치겠습니다.\n"
                    "좋습니다. 금요일 배포로 확정하겠습니다."
                ),
            )
        )

    result = asyncio.run(run())

    assert result.meeting_id == meeting_id
    assert result.status == "DRAFT"
    assert result.minutes_draft.summary.startswith("배포 일정 조율 회의:")
    assert result.minutes_draft.agenda_items
    assert result.minutes_draft.decisions == ["좋습니다. 금요일 배포로 확정하겠습니다."]
    assert result.editor_content.type == "doc"
