import asyncio
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import pytest

from app.core.errors import ContextNotFoundError, ResponseValidationError
from app.pipelines.transcript import normalize_raw_transcript
from app.providers.fake_context_loader import FakeMinutesContextLoader
from app.providers.fake_llm import FakeLLMProvider
from app.schemas.workflow import MinutesGenerationCommand
from app.workflows.minutes_generation import MinutesGenerationWorkflow


def command(**updates: Any) -> MinutesGenerationCommand:
    values = {
        "meeting_id": uuid4(),
        "organization_id": uuid4(),
        "host_user_id": uuid4(),
        "reviewer_user_id": uuid4(),
        "title": "배포 회의",
        "started_at": datetime(2026, 6, 1, tzinfo=timezone.utc),
        "ended_at": datetime(2026, 6, 1, 1, tzinfo=timezone.utc),
    }
    values.update(updates)
    return MinutesGenerationCommand(**values)


def test_normalize_raw_transcript_preserves_lines_and_removes_empty_space() -> None:
    cleaned = normalize_raw_transcript(" 첫   번째 \n\n 두  번째 ")

    assert cleaned == "첫 번째\n두 번째"


def test_fake_provider_is_deterministic() -> None:
    workflow = MinutesGenerationWorkflow(
        context_loader=FakeMinutesContextLoader(),
        llm_provider=FakeLLMProvider("fake"),
        prompt_version="minutes-v1",
    )

    first = asyncio.run(workflow.execute(command()))
    second_command = command(
        meeting_id=first.meeting_id,
        organization_id=uuid4(),
        reviewer_user_id=first.reviewer_user_id,
    )
    second = asyncio.run(workflow.execute(second_command))

    assert first.minutes_draft == second.minutes_draft
    assert first.editor_content == second.editor_content


def test_workflow_rejects_invalid_provider_result() -> None:
    class InvalidProvider:
        model_name = "invalid"

        async def generate_minutes(self, **_: Any) -> dict[str, Any]:
            return {"summary": ""}

    workflow = MinutesGenerationWorkflow(
        context_loader=FakeMinutesContextLoader(),
        llm_provider=InvalidProvider(),
        prompt_version="minutes-v1",
    )

    with pytest.raises(ResponseValidationError):
        asyncio.run(workflow.execute(command()))


def test_workflow_rejects_empty_transcript_context() -> None:
    workflow = MinutesGenerationWorkflow(
        context_loader=FakeMinutesContextLoader(),
        llm_provider=FakeLLMProvider("fake"),
        prompt_version="minutes-v1",
    )

    with pytest.raises(ContextNotFoundError):
        asyncio.run(workflow.execute(command(raw_transcript=" \n ")))
