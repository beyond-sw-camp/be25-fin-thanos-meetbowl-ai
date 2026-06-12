from typing import Protocol

from app.schemas.chat import ChatCommand, ChatResult


class ChatProvider(Protocol):
    async def answer(self, command: ChatCommand) -> ChatResult: ...
