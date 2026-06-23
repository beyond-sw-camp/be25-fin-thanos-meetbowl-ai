import logging

from app.ports.chat_provider import ChatProvider
from app.rag.chat_router import route_chat_mode
from app.schemas.chat import ChatCommand, ChatResult

logger = logging.getLogger("uvicorn.error")


class RoutingChatProvider:
    """질문 종류에 따라 no_search, single_pass, agentic 경로로 분기하는 provider.

    분기는 LLM 없는 규칙(`route_chat_mode`)이라 지연을 추가하지 않는다.
    no_search는 agentic provider의 시스템 프롬프트가 검색 도구를 생략하게 하고, 내용 질의는
    빠른 single_pass로, 날짜·건수·열거 질의는 agentic으로 보낸다.
    """

    def __init__(
        self, *, single_pass: ChatProvider, agentic: ChatProvider
    ) -> None:
        self._single_pass = single_pass
        self._agentic = agentic

    async def answer(self, command: ChatCommand) -> ChatResult:
        mode = route_chat_mode(command.question)
        logger.info("[chat-router] mode=%s question=%r", mode, command.question)
        provider = self._single_pass if mode == "single_pass" else self._agentic
        return await provider.answer(command)
