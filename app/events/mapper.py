from datetime import datetime, timezone
from uuid import UUID, uuid4

from pydantic import ValidationError

from app.core.errors import AiError
from app.schemas.events import (
    DocumentIndexRequestedPayload,
    EventEnvelope,
    MeetingEndedPayload,
    MinutesGeneratedPayload,
    MinutesGenerationRequestedPayload,
)
from app.schemas.indexing import IndexDocumentCommand
from app.schemas.workflow import MinutesGenerationCommand, MinutesGenerationResult

MEETING_ENDED = "meeting.ended"
MINUTES_GENERATION_REQUESTED = "minutes.generation.requested"
MINUTES_GENERATED = "minutes.generated"
DOCUMENT_INDEX_REQUESTED = "document.index.requested"


def command_from_event(envelope: EventEnvelope) -> MinutesGenerationCommand:
    try:
        if envelope.event_type == MEETING_ENDED:
            payload = MeetingEndedPayload.model_validate(envelope.payload)
            return MinutesGenerationCommand(**payload.model_dump())
        if envelope.event_type == MINUTES_GENERATION_REQUESTED:
            payload = MinutesGenerationRequestedPayload.model_validate(envelope.payload)
            return MinutesGenerationCommand(**payload.model_dump())
    except ValidationError as exc:
        raise AiError("AI_INVALID_EVENT", "이벤트 payload가 올바르지 않습니다.") from exc
    raise AiError("AI_INVALID_EVENT", f"지원하지 않는 이벤트입니다: {envelope.event_type}")


def generated_event(
    *, result: MinutesGenerationResult, correlation_id: UUID
) -> EventEnvelope:
    payload = MinutesGeneratedPayload(
        meeting_id=result.meeting_id,
        organization_id=result.organization_id,
        reviewer_user_id=result.reviewer_user_id,
        status="DRAFT",
        summary=result.minutes_draft.summary,
        agenda_items=result.minutes_draft.agenda_items,
        decisions=result.minutes_draft.decisions,
        action_items=result.minutes_draft.action_items,
        editor_content=result.editor_content,
        model=result.model,
        prompt_version=result.prompt_version,
    )
    return EventEnvelope(
        event_id=uuid4(),
        event_type=MINUTES_GENERATED,
        occurred_at=datetime.now(timezone.utc),
        producer="ai-server",
        version=1,
        correlation_id=correlation_id,
        payload=payload.model_dump(mode="json", by_alias=True),
    )


def index_command_from_event(envelope: EventEnvelope) -> IndexDocumentCommand:
    if envelope.event_type != DOCUMENT_INDEX_REQUESTED:
        raise AiError("AI_INVALID_EVENT", f"지원하지 않는 이벤트입니다: {envelope.event_type}")
    try:
        payload = DocumentIndexRequestedPayload.model_validate(envelope.payload)
    except ValidationError as exc:
        raise AiError("AI_INVALID_EVENT", "이벤트 payload가 올바르지 않습니다.") from exc
    return IndexDocumentCommand(
        **payload.model_dump(),
        created_at=envelope.occurred_at,
    )
