from typing import Protocol

from app.schemas.chat import ChatRequest, ChatResult


class ChatProvider(Protocol):
    async def answer(self, request: ChatRequest) -> ChatResult: ...
