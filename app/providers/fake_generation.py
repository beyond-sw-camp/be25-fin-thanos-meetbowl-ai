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
        transcript = request.prompt.rsplit("회의 원문:\n", maxsplit=1)[-1].strip()
        lines = transcript.splitlines()
        first = lines[0]
        last = lines[-1]
        title = request.prompt.split("회의 제목: ", maxsplit=1)[-1].splitlines()[0]
        output = request.response_schema.model_validate(
            {
                "summary": f"{title}: {first}",
                "agendaItems": [
                    {
                        "title": title,
                        "discussion": transcript,
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
        )
        return StructuredGenerationResult(output=output, model_name=self._model_name)
