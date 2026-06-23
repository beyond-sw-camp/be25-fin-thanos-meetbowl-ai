"""Gemini 과부하(429/503) 시 짧은 백오프 재시도와 503 전달 검증."""

import asyncio
from uuid import uuid4

import pytest
from pydantic_ai.exceptions import ModelHTTPError

from app.core.errors import ProviderUnavailableError
from app.providers.pydantic_ai_chat import PydanticAiChatProvider
from app.schemas.chat import ChatCommand


def _make_provider(agent_run, *, max_retries: int = 2) -> PydanticAiChatProvider:
    # 실제 Agent/모델 호출 없이 재시도 로직만 검증하기 위해 인스턴스를 직접 구성한다.
    provider = PydanticAiChatProvider.__new__(PydanticAiChatProvider)
    provider._embedding_provider = None
    provider._retriever = None
    provider._reranker = None
    provider._model_name = "gemini-2.5-flash"
    provider._prompt_version = "chat-v1"
    provider._candidate_pool = 30
    provider._top_n = 10
    provider._max_retries = max_retries
    provider._retry_backoff_seconds = 0.0
    provider._request_limit = 5
    provider._query_expander = None
    provider._agent = type("FakeAgent", (), {"run": staticmethod(agent_run)})()
    return provider


def _command() -> ChatCommand:
    return ChatCommand(
        request_id=uuid4(),
        correlation_id=uuid4(),
        user_id=uuid4(),
        organization_id=None,
        question="hi",
        message_history=[],
        shared_workspace_ids=[],
    )


def _http_error(status_code: int) -> ModelHTTPError:
    return ModelHTTPError(status_code=status_code, model_name="gemini-2.5-flash", body={})


def test_retries_then_succeeds_on_transient_503() -> None:
    attempts = {"n": 0}

    async def run(*_args, **_kwargs):
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise _http_error(503)
        output = type("O", (), {"answer": "ok", "cited_indices": []})()
        return type("Result", (), {"output": output})()

    provider = _make_provider(run, max_retries=2)
    result = asyncio.run(provider.answer(_command()))

    assert result.answer == "ok"
    assert attempts["n"] == 3


def test_exhausted_retries_surface_503() -> None:
    attempts = {"n": 0}

    async def run(*_args, **_kwargs):
        attempts["n"] += 1
        raise _http_error(503)

    provider = _make_provider(run, max_retries=2)
    with pytest.raises(ProviderUnavailableError) as exc:
        asyncio.run(provider.answer(_command()))

    assert exc.value.status_code == 503
    # 최초 1회 + 재시도 2회 = 3회 호출
    assert attempts["n"] == 3


def test_non_retryable_status_is_not_retried() -> None:
    attempts = {"n": 0}

    async def run(*_args, **_kwargs):
        attempts["n"] += 1
        raise _http_error(400)

    provider = _make_provider(run, max_retries=2)
    with pytest.raises(ModelHTTPError):
        asyncio.run(provider.answer(_command()))

    assert attempts["n"] == 1
