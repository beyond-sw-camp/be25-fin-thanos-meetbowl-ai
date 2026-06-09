from typing import Any

from app.schemas.workflow import MinutesGenerationContext


class FakeLLMProvider:
    def __init__(self, model_name: str) -> None:
        self._model_name = model_name

    @property
    def model_name(self) -> str:
        return self._model_name

    async def generate_minutes(
        self, *, prompt: str, context: MinutesGenerationContext
    ) -> dict[str, Any]:
        del prompt
        lines = context.raw_transcript.splitlines()
        first = lines[0]
        last = lines[-1]
        return {
            "summary": f"{context.title}: {first}",
            "agendaItems": [
                {
                    "title": context.title,
                    "discussion": context.raw_transcript,
                    "decision": last,
                }
            ],
            "decisions": [last],
            "actionItems": [
                {
                    "content": last,
                    "assigneeName": None,
                    "dueDate": None,
                }
            ],
        }
