from app.schemas.minutes import ActionItem, MinutesDraft
from app.schemas.tiptap import TiptapDocument, TiptapNode


def minutes_draft_to_tiptap(draft: MinutesDraft) -> TiptapDocument:
    """Convert validated AI data into a deterministic Tiptap StarterKit document.

    Gemini does not generate editor nodes directly. Keeping this conversion in code
    prevents malformed editor JSON and makes presentation changes independent from prompts.
    """
    content = [
        _heading("회의록", level=1),
        _heading("회의 요약", level=2),
        _paragraph(draft.summary),
    ]

    # 회의 성격에 따라 존재하는 내용만 문서화하고, 빈 섹션은 만들지 않는다.
    if draft.agenda_items:
        content.append(_heading("안건별 논의", level=2))
        for agenda in draft.agenda_items:
            content.extend([_heading(agenda.title, level=3), _paragraph(agenda.discussion)])
            if agenda.decision:
                content.append(_paragraph(f"결정: {agenda.decision}"))

    if draft.decisions:
        content.extend([_heading("결정사항", level=2), _bullet_list(draft.decisions)])

    if draft.action_items:
        content.extend(
            [
                _heading("후속 조치", level=2),
                _bullet_list([_format_action_item(item) for item in draft.action_items]),
            ]
        )
    return TiptapDocument(type="doc", content=content)


def _format_action_item(item: ActionItem) -> str:
    details: list[str] = []
    if item.assignee_name:
        details.append(f"담당: {item.assignee_name}")
    if item.due_date:
        details.append(f"기한: {item.due_date.isoformat()}")
    return f"{item.content} ({', '.join(details)})" if details else item.content


def _heading(text: str, *, level: int) -> TiptapNode:
    return TiptapNode(
        type="heading",
        attrs={"level": level},
        content=[TiptapNode(type="text", text=text)],
    )


def _paragraph(text: str) -> TiptapNode:
    return TiptapNode(type="paragraph", content=[TiptapNode(type="text", text=text)])


def _bullet_list(items: list[str]) -> TiptapNode:
    return TiptapNode(
        type="bulletList",
        content=[
            TiptapNode(type="listItem", content=[_paragraph(item)]) for item in items
        ],
    )
