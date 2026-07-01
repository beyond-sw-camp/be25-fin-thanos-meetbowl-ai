from typing import Any

from app.schemas.chat import ChatCommand


def build_chat_access_filter(
    command: ChatCommand, *, source_types: list[str] | None = None
) -> dict[str, Any]:
    """BE가 계산한 현재 권한만 사용해 Qdrant 검색 범위를 구성한다.

    접근 판정은 소유자(ownerUserId), 명시 열람 사용자(allowedUserIds), 공유 워크스페이스 범위로 한다.
    이 값들은 BE가 매 요청/색인 시점에 계산한 권한 범위라, 조직 경계(organizationId) 없이도 타 사용자
    자료가 노출되지 않는다. 덕분에 조직 미소속 사용자도 본인 개인자료와 접근 가능한 공유 자료를 검색할 수 있다.

    `source_types`가 주어지면 해당 자료 유형으로 검색을 좁힌다(권한은 그대로 유지).
    """
    access_should: list[dict[str, Any]] = [
        {"key": "ownerUserId", "match": {"value": str(command.user_id)}},
        {"key": "allowedUserIds", "match": {"any": [str(command.user_id)]}},
    ]
    if command.shared_workspace_ids:
        workspace_ids = [str(value) for value in command.shared_workspace_ids]
        access_should.extend(
            [
                {"key": "workspaceId", "match": {"any": workspace_ids}},
                {"key": "sharedWorkspaceIds", "match": {"any": workspace_ids}},
            ]
        )
    must: list[dict[str, Any]] = [{"should": access_should}]
    # 의도가 특정 유형으로 명확할 때만 자료 유형 조건을 추가로 좁힌다.
    if source_types:
        must.append({"key": "sourceType", "match": {"any": list(source_types)}})
    return {"must": must}
