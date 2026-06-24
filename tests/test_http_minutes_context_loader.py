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
