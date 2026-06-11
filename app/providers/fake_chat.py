from app.schemas.chat import ChatRequest, ChatResult


class FakeChatProvider:
    def __init__(self, model_name: str, prompt_version: str) -> None:
        self._model_name = model_name
        self._prompt_version = prompt_version

    async def answer(self, request: ChatRequest) -> ChatResult:
        del request
        return ChatResult(
            answer="검색 가능한 자료에서 질문의 근거를 확인하지 못했습니다.",
            sources=[],
            model=self._model_name,
            prompt_version=self._prompt_version,
        )
