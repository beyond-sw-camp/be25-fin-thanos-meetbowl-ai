from __future__ import annotations

from typing import Any

import httpx
from pydantic import ValidationError

from app.core.errors import AiError, ContextNotFoundError
from app.pipelines.transcript import transcript_to_segments
from app.schemas.workflow import MinutesGenerationCommand, MinutesGenerationContext


class HttpMinutesContextLoader:
    """Load the authoritative meeting metadata and Final Transcript from meetbowl-be."""

    def __init__(
        self,
        *,
        base_url: str,
        internal_token: str,
        timeout_seconds: float,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._internal_token = internal_token
        self._timeout_seconds = timeout_seconds
        self._client = client

    async def load(self, command: MinutesGenerationCommand) -> MinutesGenerationContext:
        # REST generation already contains a complete context. RabbitMQ commands intentionally do not
        # carry the transcript, so only that path calls the BE internal API.
        if self._has_inline_context(command):
            return self._inline_context(command)

        if self._client is not None:
            response = await self._request(self._client, command.meeting_id)
        else:
            async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                response = await self._request(client, command.meeting_id)
        context = self._parse_response(response)
        self._ensure_event_matches_context(command, context)
        return context

    async def _request(self, client: httpx.AsyncClient, meeting_id: Any) -> httpx.Response:
        try:
            return await client.get(
                f"{self._base_url}/api/v1/internal/meetings/{meeting_id}/minutes-generation-context",
                headers={"X-Internal-Token": self._internal_token},
                timeout=self._timeout_seconds,
            )
        except httpx.RequestError as exc:
            raise AiError(
                "AI_CONTEXT_PROVIDER_UNAVAILABLE",
                "회의록 생성 Context API를 호출할 수 없습니다.",
                retryable=True,
                status_code=503,
            ) from exc

    @staticmethod
    def _parse_response(response: httpx.Response) -> MinutesGenerationContext:
        if response.status_code == 404:
            raise ContextNotFoundError()
        if response.status_code >= 500:
            raise AiError(
                "AI_CONTEXT_PROVIDER_UNAVAILABLE",
                "회의록 생성 Context API가 일시적으로 실패했습니다.",
                retryable=True,
                status_code=503,
            )
        if response.status_code >= 400:
            error_code = None
            try:
                error_code = response.json().get("error", {}).get("code")
            except ValueError:
                pass
            # 회의 종료와 마지막 Transcript 저장은 서로 다른 RabbitMQ 흐름이라 잠시 역전될 수 있다.
            if error_code == "MINUTES_TRANSCRIPT_REQUIRED":
                raise AiError(
                    "AI_CONTEXT_TRANSCRIPT_PENDING",
                    "Final Transcript 저장을 기다리고 있습니다.",
                    retryable=True,
                    status_code=503,
                )
            raise AiError(
                "AI_CONTEXT_INVALID",
                "회의록 생성 Context를 조회할 수 없습니다.",
                status_code=422,
            )
        try:
            payload = response.json()
            if payload.get("success") is not True:
                raise ValueError("unsuccessful response")
            return MinutesGenerationContext.model_validate(payload["data"])
        except (ValueError, KeyError, ValidationError) as exc:
            raise AiError(
                "AI_CONTEXT_INVALID",
                "회의록 생성 Context 응답이 올바르지 않습니다.",
                status_code=502,
            ) from exc

    @staticmethod
    def _ensure_event_matches_context(
        command: MinutesGenerationCommand, context: MinutesGenerationContext
    ) -> None:
        if (
            context.meeting_id != command.meeting_id
            or context.organization_id != command.organization_id
            or context.reviewer_user_id != command.reviewer_user_id
        ):
            raise AiError(
                "AI_CONTEXT_MISMATCH",
                "회의 종료 이벤트와 조회된 회의 Context가 일치하지 않습니다.",
                status_code=409,
            )

    @staticmethod
    def _has_inline_context(command: MinutesGenerationCommand) -> bool:
        return all(
            value is not None
            for value in (
                command.host_user_id,
                command.title,
                command.started_at,
                command.ended_at,
                command.participants,
                command.raw_transcript,
            )
        )

    @staticmethod
    def _inline_context(command: MinutesGenerationCommand) -> MinutesGenerationContext:
        return MinutesGenerationContext(
            meeting_id=command.meeting_id,
            organization_id=command.organization_id,
            host_user_id=command.host_user_id,
            reviewer_user_id=command.reviewer_user_id,
            title=command.title,
            started_at=command.started_at,
            ended_at=command.ended_at,
            participants=command.participants,
            segments=transcript_to_segments(command.raw_transcript),
            raw_transcript=command.raw_transcript,
        )
