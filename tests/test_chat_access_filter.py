"""RAG 권한 필터(조직/소유자/공유 워크스페이스 조건) 생성 단위 테스트."""

from uuid import UUID, uuid4

from app.rag.access_filter import build_chat_access_filter
from app.schemas.chat import ChatCommand


def command(*, workspace_ids: list[UUID] | None = None) -> ChatCommand:
    return ChatCommand(
        request_id=uuid4(),
        correlation_id=uuid4(),
        user_id=uuid4(),
        organization_id=uuid4(),
        question="배포 일정을 알려줘",
        shared_workspace_ids=workspace_ids or [],
    )


def test_access_filter_always_limits_organization_and_owner() -> None:
    chat_command = command()

    result = build_chat_access_filter(chat_command)

    assert result == {
        "must": [
            {
                "key": "organizationId",
                "match": {"value": str(chat_command.organization_id)},
            },
            {
                "should": [
                    {
                        "key": "ownerUserId",
                        "match": {"value": str(chat_command.user_id)},
                    }
                ]
            },
        ]
    }


def test_access_filter_adds_only_workspaces_calculated_by_be() -> None:
    workspace_ids = [uuid4(), uuid4()]
    chat_command = command(workspace_ids=workspace_ids)

    result = build_chat_access_filter(chat_command)
    access_conditions = result["must"][1]["should"]

    assert access_conditions[1]["match"]["any"] == [
        str(workspace_id) for workspace_id in workspace_ids
    ]
    assert access_conditions[2]["match"]["any"] == [
        str(workspace_id) for workspace_id in workspace_ids
    ]


def test_access_filter_without_source_types_has_no_type_condition() -> None:
    result = build_chat_access_filter(command())

    assert all(condition.get("key") != "sourceType" for condition in result["must"])


def test_access_filter_narrows_to_requested_source_types() -> None:
    result = build_chat_access_filter(
        command(), source_types=["BACKUP_MAIL", "MINUTES"]
    )

    type_conditions = [c for c in result["must"] if c.get("key") == "sourceType"]
    # 권한 조건은 유지하면서 자료 유형만 추가로 좁힌다.
    assert type_conditions == [
        {"key": "sourceType", "match": {"any": ["BACKUP_MAIL", "MINUTES"]}}
    ]
