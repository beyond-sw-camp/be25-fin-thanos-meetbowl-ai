from uuid import uuid4

from app.rag.access_filter import build_chat_access_filter
from app.schemas.chat import ChatCommand


def test_chat_filter_includes_minutes_allowed_user_scope() -> None:
    user_id = uuid4()
    command = ChatCommand(
        request_id=uuid4(),
        correlation_id=uuid4(),
        user_id=user_id,
        organization_id=uuid4(),
        question="지난 회의록 알려줘",
        message_history=[],
        shared_workspace_ids=[],
    )

    access_filter = build_chat_access_filter(command, source_types=["MINUTES"])

    assert access_filter["must"][0]["should"] == [
        {"key": "ownerUserId", "match": {"value": str(user_id)}},
        {"key": "allowedUserIds", "match": {"any": [str(user_id)]}},
    ]
    assert access_filter["must"][1] == {
        "key": "sourceType",
        "match": {"any": ["MINUTES"]},
    }


def test_chat_filter_includes_shared_workspace_scope() -> None:
    user_id = uuid4()
    workspace_id = uuid4()
    command = ChatCommand(
        request_id=uuid4(),
        correlation_id=uuid4(),
        user_id=user_id,
        organization_id=uuid4(),
        question="공유 자료 찾아줘",
        message_history=[],
        shared_workspace_ids=[workspace_id],
    )

    access_filter = build_chat_access_filter(command)

    assert access_filter["must"][0]["should"] == [
        {"key": "ownerUserId", "match": {"value": str(user_id)}},
        {"key": "allowedUserIds", "match": {"any": [str(user_id)]}},
        {"key": "workspaceId", "match": {"any": [str(workspace_id)]}},
        {"key": "sharedWorkspaceIds", "match": {"any": [str(workspace_id)]}},
    ]
