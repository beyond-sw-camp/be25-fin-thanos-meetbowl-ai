from datetime import datetime, timezone

from pydantic import ValidationError

from app.core.errors import ContextNotFoundError, ResponseValidationError
from app.pipelines.transcript import normalize_raw_transcript
from app.pipelines.tiptap import minutes_draft_to_tiptap
from app.ports.context_loader import MinutesContextLoader
from app.ports.llm_provider import LLMProvider
from app.prompts.minutes import build_minutes_prompt
from app.schemas.minutes import MinutesDraft
from app.schemas.workflow import MinutesGenerationCommand, MinutesGenerationResult


class MinutesGenerationWorkflow:
    def __init__(
        self,
        *,
        context_loader: MinutesContextLoader,
        llm_provider: LLMProvider,
        prompt_version: str,
    ) -> None:
        self._context_loader = context_loader
        self._llm_provider = llm_provider
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
        raw_result = await self._llm_provider.generate_minutes(prompt=prompt, context=context)
        try:
            draft = MinutesDraft.model_validate(raw_result)
        except ValidationError as exc:
            raise ResponseValidationError() from exc
        return MinutesGenerationResult(
            meeting_id=context.meeting_id,
            reviewer_user_id=context.reviewer_user_id,
            status="DRAFT",
            minutes_draft=draft,
            editor_content=minutes_draft_to_tiptap(draft),
            model=self._llm_provider.model_name,
            prompt_version=prompt_version,
            generated_at=datetime.now(timezone.utc),
        )
