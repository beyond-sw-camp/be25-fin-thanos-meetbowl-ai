from app.ports.chat_provider import ChatProvider
from app.schemas.chat import ChatRequest, ChatResult


class ChatWorkflow:
    def __init__(self, provider: ChatProvider) -> None:
        self._provider = provider

    async def execute(self, request: ChatRequest) -> ChatResult:
        return await self._provider.answer(request)
