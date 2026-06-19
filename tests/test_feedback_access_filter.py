from uuid import uuid4

from app.rag.feedback_access_filter import build_feedback_access_filter
from app.schemas.feedback import FeedbackTranscriptSegment, MeetingFeedbackCommand


def test_feedback_filter_requires_every_authenticated_participant() -> None:
    meeting_id = uuid4()
    organization_id = uuid4()
    participant_a = uuid4()
    participant_b = uuid4()
    command = MeetingFeedbackCommand(
        meeting_id=meeting_id,
        session_id=uuid4(),
        organization_id=organization_id,
        participant_user_ids=[participant_b, participant_a, participant_b],
        correlation_id=uuid4(),
        transcript_window=[
            FeedbackTranscriptSegment(
                segment_id=uuid4(),
                sequence=1,
                language="ko",
                text="이 안건은 이전에도 논의했습니다.",
                started_at_ms=1_000,
                ended_at_ms=2_000,
            )
        ],
    )

    access_filter = build_feedback_access_filter(
        command, exclude_meeting_id=str(meeting_id)
    )

    assert access_filter["must"][:2] == [
        {
            "key": "organizationId",
            "match": {"value": str(organization_id)},
        },
        {"key": "sourceType", "match": {"any": ["MEETING_MINUTES", "MINUTES"]}},
    ]
    assert access_filter["must"][2:] == [
        {"key": "allowedUserIds", "match": {"any": [str(user_id)]}}
        for user_id in sorted({participant_a, participant_b}, key=str)
    ]
    assert access_filter["must_not"] == [
        {"key": "metadata.meetingId", "match": {"value": str(meeting_id)}}
    ]
