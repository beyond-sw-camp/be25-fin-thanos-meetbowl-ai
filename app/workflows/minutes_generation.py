from datetime import datetime, timezone

from pydantic import ValidationError

from app.core.errors import ContextNotFoundError, ResponseValidationError
from app.pipelines.minutes_evidence import evidence_to_minutes_draft, finalize_minutes_evidence
from app.pipelines.minutes_quality import finalize_minutes_draft
from app.pipelines.transcript import (
    mark_suspicious_segments,
    normalize_raw_transcript,
    transcript_to_segments,
)
from app.pipelines.tiptap import minutes_draft_to_tiptap
from app.ports.context_loader import MinutesContextLoader
from app.ports.generation import (
    StructuredGenerationPort,
    StructuredGenerationRequest,
)
from app.prompts.minutes import build_minutes_evidence_prompt
from app.schemas.minutes import MinutesDraft, MinutesEvidence, TranscriptSegment
from app.schemas.workflow import (
    MinutesGenerationCommand,
    MinutesGenerationContext,
    MinutesGenerationResult,
)


class MinutesGenerationWorkflow:
    def __init__(
        self,
        *,
        context_loader: MinutesContextLoader,
        structured_generation_port: StructuredGenerationPort,
        model_profile: str,
        prompt_version: str,
    ) -> None:
        self._context_loader = context_loader
        self._structured_generation_port = structured_generation_port
        self._model_profile = model_profile
        self._prompt_version = prompt_version

    async def execute(self, command: MinutesGenerationCommand) -> MinutesGenerationResult:
        context = await self._context_loader.load(command)
        segments = self._segments_from_context(context)
        raw_transcript = normalize_raw_transcript(context.raw_transcript)
        if segments:
            raw_transcript = normalize_raw_transcript(
                "\n".join(segment.source_text for segment in segments)
            )
        if not raw_transcript:
            raise ContextNotFoundError("회의록을 생성할 회의 원문이 없습니다.")
        # 이후 생성 단계는 upstream 원문 형식이 아니라 이 긴 텍스트 계약에만 의존한다.
        context = context.model_copy(update={"raw_transcript": raw_transcript})
        if not segments:
            segments = transcript_to_segments(raw_transcript)
        segments = mark_suspicious_segments(segments)
        prompt_version = command.prompt_version or self._prompt_version
        prompt = build_minutes_evidence_prompt(
            prompt_version=prompt_version,
            context=context,
            segments=segments,
        )
        generation_result = await self._structured_generation_port.generate_structured(
            StructuredGenerationRequest(
                prompt=prompt,
                response_schema=MinutesEvidence,
                model_profile=self._model_profile,
            )
        )
        try:
            evidence = MinutesEvidence.model_validate(generation_result.output)
        except ValidationError as exc:
            raise ResponseValidationError() from exc
        evidence = finalize_minutes_evidence(evidence=evidence, segments=segments)
        draft = evidence_to_minutes_draft(evidence)
        draft = finalize_minutes_draft(raw_transcript=raw_transcript, draft=draft)
        return MinutesGenerationResult(
            meeting_id=context.meeting_id,
            organization_id=context.organization_id,
            reviewer_user_id=context.reviewer_user_id,
            status="DRAFT",
            minutes_draft=draft,
            editor_content=minutes_draft_to_tiptap(draft),
            model=generation_result.model_name,
            prompt_version=prompt_version,
            generated_at=datetime.now(timezone.utc),
        )

    @staticmethod
    def _segments_from_context(context: MinutesGenerationContext) -> list[TranscriptSegment]:
        return [
            segment
            for segment in context.segments
            if segment.source_text and segment.source_text.strip()
        ]
