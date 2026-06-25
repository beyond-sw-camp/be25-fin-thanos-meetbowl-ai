import asyncio
from datetime import datetime, timezone
from uuid import uuid4

import httpx
from app.providers.http_minutes_context_loader import HttpMinutesContextLoader
from app.schemas.workflow import MinutesGenerationCommand


def test_loads_final_transcript_context_from_be() -> None:
    meeting_id = uuid4()
    organization_id = uuid4()
    host_user_id = uuid4()
    reviewer_user_id = uuid4()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["X-Internal-Token"] == "internal-token"
        assert request.url.path.endswith(f"/{meeting_id}/minutes-generation-context")
        return httpx.Response(
            200,
            json={
                "success": True,
                "data": {
                    "meetingId": str(meeting_id),
                    "organizationId": str(organization_id),
                    "hostUserId": str(host_user_id),
                    "reviewerUserId": str(reviewer_user_id),
                    "title": "주간 회의",
                    "startedAt": "2026-06-23T01:00:00Z",
                    "endedAt": "2026-06-23T02:00:00Z",
                    "participants": [
                        {"userId": str(host_user_id), "name": "홍길동", "department": None}
                    ],
                    "segments": [
                        {
                            "segmentId": "segment-1",
                            "sequence": 1,
                            "language": "KO",
                            "sourceText": "첫 번째 확정 발화",
                            "startedAtMs": 0,
                            "endedAtMs": 500,
                        },
                        {
                            "segmentId": "segment-2",
                            "sequence": 2,
                            "language": "KO",
                            "sourceText": "두 번째 확정 발화",
                            "startedAtMs": 600,
                            "endedAtMs": 1000,
                        },
                    ],
                    "rawTranscript": "첫 번째 확정 발화\n두 번째 확정 발화",
                },
                "message": None,
            },
        )

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            loader = HttpMinutesContextLoader(
                base_url="http://be",
                internal_token="internal-token",
                timeout_seconds=1,
                client=client,
            )
            return await loader.load(
                MinutesGenerationCommand(
                    meeting_id=meeting_id,
                    organization_id=organization_id,
                    reviewer_user_id=reviewer_user_id,
                    host_user_id=host_user_id,
                    title="주간 회의",
                    started_at=datetime(2026, 6, 23, 1, tzinfo=timezone.utc),
                    ended_at=datetime(2026, 6, 23, 2, tzinfo=timezone.utc),
                )
            )

    context = asyncio.run(run())
    assert context.raw_transcript == "첫 번째 확정 발화\n두 번째 확정 발화"
    assert [segment.sequence for segment in context.segments] == [1, 2]
    assert [segment.source_text for segment in context.segments] == [
        "첫 번째 확정 발화",
        "두 번째 확정 발화",
    ]


def test_inline_rest_context_ignores_non_context_command_fields() -> None:
    meeting_id = uuid4()
    organization_id = uuid4()
    host_user_id = uuid4()
    reviewer_user_id = uuid4()
    requested_by_user_id = uuid4()

    async def run():
        loader = HttpMinutesContextLoader(
            base_url="http://be",
            internal_token="internal-token",
            timeout_seconds=1,
        )
        return await loader.load(
            MinutesGenerationCommand(
                meeting_id=meeting_id,
                organization_id=organization_id,
                reviewer_user_id=reviewer_user_id,
                host_user_id=host_user_id,
                requested_by_user_id=requested_by_user_id,
                title="주간 회의",
                started_at=datetime(2026, 6, 23, 1, tzinfo=timezone.utc),
                ended_at=datetime(2026, 6, 23, 2, tzinfo=timezone.utc),
                prompt_version="minutes-v1",
                reason="manual-test",
                participants=[],
                raw_transcript="금요일 배포로 진행합니다.",
            )
        )

    context = asyncio.run(run())
    assert context.meeting_id == meeting_id
    assert context.organization_id == organization_id
    assert context.host_user_id == host_user_id
    assert context.reviewer_user_id == reviewer_user_id
    assert context.title == "주간 회의"
    assert context.raw_transcript == "금요일 배포로 진행합니다."
    assert [segment.source_text for segment in context.segments] == ["금요일 배포로 진행합니다."]
