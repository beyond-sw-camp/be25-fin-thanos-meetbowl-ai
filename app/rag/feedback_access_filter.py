from typing import Any

from app.schemas.feedback import MeetingFeedbackCommand


def build_feedback_access_filter(
    command: MeetingFeedbackCommand, *, exclude_meeting_id: str
) -> dict[str, Any]:
    must: list[dict[str, Any]] = [
        {
            "key": "organizationId",
            "match": {"value": str(command.organization_id)},
        },
        {"key": "sourceType", "match": {"any": ["MEETING_MINUTES", "MINUTES"]}},
    ]
    for user_id in command.participant_user_ids:
        # 현재 회의 참가자 모두가 읽을 수 있는 회의록만 방송형 피드백 근거로 허용한다.
        must.append({"key": "allowedUserIds", "match": {"any": [str(user_id)]}})
    return {
        "must": must,
        "must_not": [{"key": "metadata.meetingId", "match": {"value": exclude_meeting_id}}],
    }
