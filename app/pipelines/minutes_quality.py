import re

from app.core.errors import ResponseValidationError
from app.schemas.minutes import ActionItem, AgendaItem, MinutesDraft

_QUOTE_CHARS = "\"'“”‘’「」『』"
_LOW_SIGNAL_PATTERNS = (
    "공유 링크",
    "링크 복사",
    "링크를 올릴게",
    "링크를 올릴게요",
    "링크 보낼게",
    "들리시",
    "안 들리",
    "마이크",
    "자막 발행",
    "자막 확인",
    "잠시만",
)


def finalize_minutes_draft(*, raw_transcript: str, draft: MinutesDraft) -> MinutesDraft:
    summary = _clean_text(draft.summary)
    agenda_items = _refine_agenda_items(draft.agenda_items)
    decisions = _dedupe_texts(
        text for text in (_clean_text(item) for item in draft.decisions) if _is_meaningful_text(text)
    )
    action_items = _refine_action_items(draft.action_items)

    refined = draft.model_copy(
        update={
            "summary": summary,
            "agenda_items": agenda_items,
            "decisions": decisions,
            "action_items": action_items,
        }
    )
    _validate_summary_quality(raw_transcript=raw_transcript, summary=refined.summary)
    return refined


def _refine_agenda_items(items: list[AgendaItem]) -> list[AgendaItem]:
    refined: list[AgendaItem] = []
    for item in items:
        title = _clean_text(item.title)
        discussion = _clean_text(item.discussion)
        decision = _clean_text(item.decision) if item.decision else None
        if not title or not discussion:
            continue
        if _contains_quote(title) or _contains_quote(discussion):
            continue
        if len(discussion) < 20:
            continue
        if _looks_like_operational_noise(title, discussion, decision):
            continue
        if decision and (not _is_meaningful_text(decision) or _contains_quote(decision)):
            decision = None
        refined.append(
            item.model_copy(
                update={
                    "title": title,
                    "discussion": discussion,
                    "decision": decision,
                }
            )
        )
    return refined


def _refine_action_items(items: list[ActionItem]) -> list[ActionItem]:
    refined: list[ActionItem] = []
    seen_contents: set[str] = set()
    for item in items:
        content = _clean_text(item.content)
        if not _is_meaningful_text(content) or _contains_quote(content):
            continue
        lowered = content.casefold()
        if lowered in seen_contents:
            continue
        seen_contents.add(lowered)
        refined.append(item.model_copy(update={"content": content}))
    return refined


def _validate_summary_quality(*, raw_transcript: str, summary: str) -> None:
    if len(summary) < 20:
        raise ResponseValidationError("AI 회의록 요약이 너무 짧습니다.")
    if _contains_quote(summary):
        raise ResponseValidationError("AI 회의록 요약에 원문 발화 인용이 포함되었습니다.")
    if _is_korean_dominant(raw_transcript) and not _looks_like_korean(summary):
        raise ResponseValidationError("한국어 회의 원문에 대한 요약이 한국어로 생성되지 않았습니다.")


def _looks_like_operational_noise(title: str, discussion: str, decision: str | None) -> bool:
    lowered = f"{title} {discussion} {decision or ''}".casefold()
    if not any(pattern.casefold() in lowered for pattern in _LOW_SIGNAL_PATTERNS):
        return False
    return len(discussion) < 90 and "결정" not in lowered and "합의" not in lowered


def _is_meaningful_text(text: str) -> bool:
    return bool(text) and len(text) >= 8 and not _looks_like_fragment(text)


def _looks_like_fragment(text: str) -> bool:
    return len(text.split()) <= 1 and len(text) < 10


def _contains_quote(text: str) -> bool:
    return any(char in text for char in _QUOTE_CHARS)


def _looks_like_korean(text: str) -> bool:
    hangul_count = len(re.findall(r"[가-힣]", text))
    latin_count = len(re.findall(r"[A-Za-z]", text))
    return hangul_count > 0 and hangul_count >= latin_count


def _is_korean_dominant(text: str) -> bool:
    hangul_count = len(re.findall(r"[가-힣]", text))
    latin_count = len(re.findall(r"[A-Za-z]", text))
    return hangul_count > 0 and hangul_count >= latin_count


def _clean_text(text: str | None) -> str:
    if not text:
        return ""
    return " ".join(text.split()).strip()


def _dedupe_texts(texts) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for text in texts:
        lowered = text.casefold()
        if lowered in seen:
            continue
        seen.add(lowered)
        result.append(text)
    return result
