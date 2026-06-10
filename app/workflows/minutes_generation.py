from datetime import datetime, timezone

from pydantic import ValidationError

from app.core.errors import ContextNotFoundError, ResponseValidationError
from app.pipelines.transcript import normalize_raw_transcript
from app.pipelines.tiptap import minutes_draft_to_tiptap
from app.ports.context_loader import MinutesContextLoader
from app.ports.generation import (
    StructuredGenerationPort,
    StructuredGenerationRequest,
)
from app.prompts.minutes import build_minutes_prompt
from app.schemas.minutes import MinutesDraft
from app.schemas.workflow import MinutesGenerationCommand, MinutesGenerationResult


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
        raw_transcript = normalize_raw_transcript(context.raw_transcript)
        if not raw_transcript:
            raise ContextNotFoundError("회의록을 생성할 회의 원문이 없습니다.")
        # 이후 생성 단계는 upstream 원문 형식이 아니라 이 긴 텍스트 계약에만 의존한다.
        context = context.model_copy(update={"raw_transcript": raw_transcript})
        prompt_version = command.prompt_version or self._prompt_version
        prompt = build_minutes_prompt(
            prompt_version=prompt_version,
            context=context,
        )
        generation_result = await self._structured_generation_port.generate_structured(
            StructuredGenerationRequest(
                prompt=prompt,
                response_schema=MinutesDraft,
                model_profile=self._model_profile,
            )
        )
        try:
            draft = MinutesDraft.model_validate(generation_result.output)
        except ValidationError as exc:
            raise ResponseValidationError() from exc
        return MinutesGenerationResult(
            meeting_id=context.meeting_id,
            reviewer_user_id=context.reviewer_user_id,
            status="DRAFT",
            minutes_draft=draft,
            editor_content=minutes_draft_to_tiptap(draft),
            model=generation_result.model_name,
            prompt_version=prompt_version,
            generated_at=datetime.now(timezone.utc),
        )
