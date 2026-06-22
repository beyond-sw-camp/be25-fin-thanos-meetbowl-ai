import asyncio
import json
from uuid import uuid4

import httpx

from app.rag.qdrant_feedback import QdrantMeetingFeedbackRetriever
from app.schemas.feedback import FeedbackTranscriptSegment, MeetingFeedbackCommand


def test_feedback_search_returns_dense_cosine_score() -> None:
    captured_body = None
    document_id = uuid4()
    historical_meeting_id = uuid4()

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_body
        captured_body = request.read().decode()
        return httpx.Response(
            200,
            json={
                "result": {
                    "points": [
                        {
                            "id": str(uuid4()),
                            "score": 0.91,
                            "payload": {
                                "sourceId": str(document_id),
                                "sourceType": "MINUTES",
                                "title": "과거 회의록",
                                "content": "결제 승인 정책을 확정했습니다.",
                                "metadata": {
                                    "meetingId": str(historical_meeting_id),
                                    "approvedAt": "2026-06-18T01:00:00Z",
                                },
                            },
                        }
                    ]
                }
            },
        )

    async def run():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler)
        ) as client:
            retriever = QdrantMeetingFeedbackRetriever(
                qdrant_url="http://qdrant",
                qdrant_collection="documents",
                candidate_limit=3,
                http_client=client,
            )
            command = MeetingFeedbackCommand(
                meeting_id=uuid4(),
                session_id=uuid4(),
                organization_id=uuid4(),
                participant_user_ids=[uuid4()],
                correlation_id=uuid4(),
                transcript_window=[
                    FeedbackTranscriptSegment(
                        segment_id=uuid4(),
                        sequence=0,
                        language="ko",
                        text="결제 승인 정책",
                        started_at_ms=0,
                        ended_at_ms=1,
                    )
                ],
            )
            return await retriever.search(
                vector=[0.1, 0.2], query="결제 승인 정책", command=command
            )

    candidates = asyncio.run(run())

    assert captured_body is not None
    body = json.loads(captured_body)
    assert body["query"] == [0.1, 0.2]
    assert body["using"] == "dense"
    assert "prefetch" not in body
    assert "fusion" not in body
    assert candidates[0].score == 0.91
