from datetime import date

from app.pipelines.tiptap import minutes_draft_to_tiptap
from app.schemas.minutes import ActionItem, AgendaItem, MinutesDraft


def test_converter_builds_starterkit_document() -> None:
    draft = MinutesDraft(
        summary="배포 일정을 논의했습니다.",
        agenda_items=[
            AgendaItem(
                title="배포 일정",
                discussion="금요일 배포 가능 여부를 검토했습니다.",
                decision="금요일에 배포합니다.",
            )
        ],
        decisions=["금요일에 배포합니다."],
        action_items=[
            ActionItem(
                content="배포 체크리스트 작성",
                assignee_name="홍길동",
                due_date=date(2026, 6, 12),
            )
        ],
    )

    document = minutes_draft_to_tiptap(draft)
    serialized = document.model_dump(mode="json", by_alias=True)

    assert serialized["type"] == "doc"
    assert serialized["content"][0] == {
        "type": "heading",
        "attrs": {"level": 1},
        "content": [{"type": "text", "text": "회의록"}],
    }
    assert any(node["type"] == "bulletList" for node in serialized["content"])
    assert "담당: 홍길동" in str(serialized)
    assert "기한: 2026-06-12" in str(serialized)


def test_converter_omits_empty_optional_sections() -> None:
    document = minutes_draft_to_tiptap(MinutesDraft(summary="요약"))

    serialized = document.model_dump(mode="json", by_alias=True)

    assert serialized["content"] == [
        {
            "type": "heading",
            "attrs": {"level": 1},
            "content": [{"type": "text", "text": "회의록"}],
        },
        {
            "type": "heading",
            "attrs": {"level": 2},
            "content": [{"type": "text", "text": "회의 요약"}],
        },
        {
            "type": "paragraph",
            "content": [{"type": "text", "text": "요약"}],
        },
    ]
