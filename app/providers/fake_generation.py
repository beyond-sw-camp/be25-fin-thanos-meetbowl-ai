from app.ports.generation import (
    StructuredGenerationRequest,
    StructuredGenerationResult,
)


class FakeStructuredGenerationProvider:
    def __init__(self, model_name: str) -> None:
        self._model_name = model_name

    async def generate_structured(
        self, request: StructuredGenerationRequest
    ) -> StructuredGenerationResult:
        transcript = request.prompt.rsplit("Transcript Segments:\n", maxsplit=1)[-1].strip()
        lines = [line.strip() for line in transcript.splitlines() if line.strip()]
        normalized = [line.split(". ", maxsplit=1)[-1] if ". " in line else line for line in lines]
        normalized = [
            line.split("] ", maxsplit=1)[-1] if line.startswith("[") and "] " in line else line
            for line in normalized
        ]
        first = normalized[0]
        last = normalized[-1]
        title = request.prompt.split("회의 제목: ", maxsplit=1)[-1].splitlines()[0]
        output = request.response_schema.model_validate(
            {
                "summary": f"{title}: {first}",
                "agendaItems": [
                    {
                        "title": title,
                        "discussionPoints": normalized,
                        "sourceSequences": list(range(1, len(normalized) + 1)),
                        "decision": last,
                    }
                ],
                "decisions": [
                    {
                        "content": last,
                        "sourceSequences": [len(normalized)],
                    }
                ],
                "actionItems": [
                    {
                        "content": last,
                        "assigneeName": None,
                        "dueDate": None,
                        "sourceSequences": [len(normalized)],
                    }
                ],
            }
        )
        return StructuredGenerationResult(output=output, model_name=self._model_name)
