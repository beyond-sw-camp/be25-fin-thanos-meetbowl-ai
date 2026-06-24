from app.schemas.minutes import (
    ActionItem,
    AgendaItem,
    EvidenceActionItem,
    EvidenceAgendaItem,
    EvidenceDecision,
    MinutesDraft,
    MinutesEvidence,
    TranscriptSegment,
)


def finalize_minutes_evidence(
    *,
    evidence: MinutesEvidence,
    segments: list[TranscriptSegment],
) -> MinutesEvidence:
    valid_sequences = {segment.sequence for segment in segments}
    suspicious_sequences = {segment.sequence for segment in segments if segment.suspicious}
    refined_agenda_items = [
        refined
        for item in evidence.agenda_items
        if (
            refined := _refine_evidence_agenda_item(
                item,
                valid_sequences,
                suspicious_sequences,
            )
        )
        is not None
    ]
    refined_decisions = [
        refined
        for item in evidence.decisions
        if (
            refined := _refine_evidence_decision(
                item,
                valid_sequences,
                suspicious_sequences,
            )
        )
        is not None
    ]
    refined_action_items = [
        refined
        for item in evidence.action_items
        if (
            refined := _refine_evidence_action_item(
                item,
                valid_sequences,
                suspicious_sequences,
            )
        )
        is not None
    ]
    return evidence.model_copy(
        update={
            "summary": evidence.summary,
            "agenda_items": refined_agenda_items,
            "decisions": refined_decisions,
            "action_items": refined_action_items,
        }
    )


def evidence_to_minutes_draft(evidence: MinutesEvidence) -> MinutesDraft:
    return MinutesDraft(
        summary=evidence.summary,
        agenda_items=[_agenda_item(item) for item in evidence.agenda_items],
        decisions=_unique_preserve_order(
            decision.content for decision in evidence.decisions if decision.content
        ),
        action_items=_action_items(evidence.action_items),
    )


def _agenda_item(item: EvidenceAgendaItem) -> AgendaItem:
    discussion = " ".join(point.strip() for point in item.discussion_points if point.strip()).strip()
    if not discussion:
        discussion = item.title
    return AgendaItem(
        title=item.title,
        discussion=discussion,
        decision=item.decision,
    )


def _refine_evidence_agenda_item(
    item: EvidenceAgendaItem,
    valid_sequences: set[int],
    suspicious_sequences: set[int],
) -> EvidenceAgendaItem | None:
    sequences = _sanitize_sequences(item.source_sequences, valid_sequences)
    discussion_points = _unique_texts(item.discussion_points, limit=3)
    if not item.title.strip() or not sequences:
        return None
    if _all_suspicious(sequences, suspicious_sequences):
        return None
    if len(sequences) < 2 and not item.decision:
        return None
    if not discussion_points:
        return None
    return item.model_copy(
        update={
            "title": item.title.strip(),
            "discussion_points": discussion_points,
            "source_sequences": sequences,
            "decision": item.decision.strip() if item.decision else None,
        }
    )


def _refine_evidence_decision(
    item: EvidenceDecision,
    valid_sequences: set[int],
    suspicious_sequences: set[int],
) -> EvidenceDecision | None:
    sequences = _sanitize_sequences(item.source_sequences, valid_sequences)
    content = item.content.strip()
    if not content or not sequences or _all_suspicious(sequences, suspicious_sequences):
        return None
    return item.model_copy(update={"content": content, "source_sequences": sequences})


def _refine_evidence_action_item(
    item: EvidenceActionItem,
    valid_sequences: set[int],
    suspicious_sequences: set[int],
) -> EvidenceActionItem | None:
    sequences = _sanitize_sequences(item.source_sequences, valid_sequences)
    content = item.content.strip()
    if not content or not sequences or _all_suspicious(sequences, suspicious_sequences):
        return None
    return item.model_copy(update={"content": content, "source_sequences": sequences})


def _action_items(items: list[EvidenceActionItem]) -> list[ActionItem]:
    deduped: list[ActionItem] = []
    seen: set[tuple[str, str | None, str | None]] = set()
    for item in items:
        key = (
            item.content.casefold(),
            item.assignee_name.casefold() if item.assignee_name else None,
            item.due_date.isoformat() if item.due_date else None,
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(
            ActionItem(
                content=item.content,
                assignee_name=item.assignee_name,
                due_date=item.due_date,
            )
        )
    return deduped


def _unique_preserve_order(values) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        lowered = value.casefold()
        if lowered in seen:
            continue
        seen.add(lowered)
        result.append(value)
    return result


def _sanitize_sequences(
    source_sequences: list[int],
    valid_sequences: set[int],
) -> list[int]:
    result: list[int] = []
    seen: set[int] = set()
    for sequence in sorted(source_sequences):
        if sequence not in valid_sequences or sequence in seen:
            continue
        seen.add(sequence)
        result.append(sequence)
    return result


def _all_suspicious(
    source_sequences: list[int],
    suspicious_sequences: set[int],
) -> bool:
    return bool(source_sequences) and all(
        sequence in suspicious_sequences for sequence in source_sequences
    )


def _unique_texts(values: list[str], *, limit: int) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = " ".join(value.split()).strip()
        if not normalized:
            continue
        lowered = normalized.casefold()
        if lowered in seen:
            continue
        seen.add(lowered)
        result.append(normalized)
        if len(result) >= limit:
            break
    return result
