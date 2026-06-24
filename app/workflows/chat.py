from app.ports.chat_provider import ChatProvider
from app.schemas.chat import ChatCommand, ChatResult


class ChatWorkflow:
    def __init__(self, provider: ChatProvider) -> None:
        self._provider = provider

    async def execute(self, command: ChatCommand) -> ChatResult:
        return await self._provider.answer(command)
