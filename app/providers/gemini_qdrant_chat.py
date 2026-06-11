from typing import Any

import httpx
from google import genai
from google.genai import types
from pydantic import ValidationError

from app.core.errors import ProviderUnavailableError, ResponseValidationError
from app.prompts.chat import build_chat_prompt
from app.schemas.chat import (
    ChatRequest,
    ChatResult,
    ChatSource,
    GeneratedChatAnswer,
)


class GeminiQdrantChatProvider:
    def __init__(
        self,
        *,
        api_key: str | None,
        model_name: str,
        embedding_model_name: str,
        temperature: float,
        qdrant_url: str,
        qdrant_collection: str,
        prompt_version: str,
        client: Any | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._api_key = api_key
        self._model_name = model_name
        self._embedding_model_name = embedding_model_name
        self._temperature = temperature
        self._qdrant_url = qdrant_url.rstrip("/")
        self._qdrant_collection = qdrant_collection
        self._prompt_version = prompt_version
        self._client = client
        self._http_client = http_client

    async def answer(self, request: ChatRequest) -> ChatResult:
        vector = await self._embed(request.question)
        sources = await self._search(vector, request)
        if not sources:
            return ChatResult(
                answer="검색 가능한 자료에서 질문의 근거를 확인하지 못했습니다.",
                sources=[],
                model=self._model_name,
                prompt_version=self._prompt_version,
            )

        prompt = build_chat_prompt(
            question=request.question,
            history=request.message_history,
            sources=sources,
        )
        generated = await self._generate(prompt)
        return ChatResult(
            answer=generated.answer,
            sources=sources,
            model=self._model_name,
            prompt_version=self._prompt_version,
        )

    async def _embed(self, text: str) -> list[float]:
        client = self._get_client()
        try:
            response = await client.aio.models.embed_content(
                model=self._embedding_model_name,
                contents=text,
            )
            values = response.embeddings[0].values
            if not values:
                raise ProviderUnavailableError("Gemini가 빈 임베딩을 반환했습니다.")
            return list(values)
        except ProviderUnavailableError:
            raise
        except Exception as exc:
            raise ProviderUnavailableError("질문 임베딩 생성에 실패했습니다.") from exc

    async def _search(self, vector: list[float], request: ChatRequest) -> list[ChatSource]:
        access_should: list[dict[str, Any]] = [
            {"key": "ownerUserId", "match": {"value": str(request.user_id)}}
        ]
        if request.shared_workspace_ids:
            workspace_ids = [str(value) for value in request.shared_workspace_ids]
            access_should.extend(
                [
                    {"key": "workspaceId", "match": {"any": workspace_ids}},
                    {"key": "sharedWorkspaceIds", "match": {"any": workspace_ids}},
                ]
            )
        body = {
            "query": vector,
            "filter": {
                "must": [
                    {
                        "key": "organizationId",
                        "match": {"value": str(request.organization_id)},
                    },
                    {"should": access_should},
                ]
            },
            "limit": 10,
            "with_payload": True,
        }
        try:
            client = self._http_client or httpx.AsyncClient(timeout=10.0)
            response = await client.post(
                f"{self._qdrant_url}/collections/{self._qdrant_collection}/points/query",
                json=body,
            )
            response.raise_for_status()
            result = response.json().get("result", {})
            points = result.get("points", result if isinstance(result, list) else [])
            return self._to_sources(points)
        except Exception as exc:
            raise ProviderUnavailableError("Qdrant 검색에 실패했습니다.") from exc
        finally:
            if self._http_client is None and "client" in locals():
                await client.aclose()

    def _to_sources(self, points: list[dict[str, Any]]) -> list[ChatSource]:
        sources: list[ChatSource] = []
        for point in points:
            payload = point.get("payload") or {}
            try:
                snippet = payload.get("snippet") or payload.get("content")
                sources.append(
                    ChatSource(
                        type=payload["sourceType"],
                        resource_id=payload.get("sourceId") or payload["documentId"],
                        title=payload["title"],
                        snippet=snippet,
                        score=max(0.0, min(1.0, float(point.get("score", 0.0)))),
                    )
                )
            except (KeyError, TypeError, ValueError, ValidationError):
                continue
        return sources

    async def _generate(self, prompt: str) -> GeneratedChatAnswer:
        client = self._get_client()
        try:
            response = await client.aio.models.generate_content(
                model=self._model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=self._temperature,
                    response_mime_type="application/json",
                    response_json_schema=GeneratedChatAnswer.model_json_schema(by_alias=True),
                ),
            )
            if not response.text:
                raise ResponseValidationError("Gemini가 빈 챗봇 응답을 반환했습니다.")
            return GeneratedChatAnswer.model_validate_json(response.text)
        except ResponseValidationError:
            raise
        except ValidationError as exc:
            raise ResponseValidationError() from exc
        except Exception as exc:
            raise ProviderUnavailableError() from exc

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        if not self._api_key:
            raise ProviderUnavailableError("GEMINI_API_KEY가 설정되지 않았습니다.")
        self._client = genai.Client(api_key=self._api_key)
        return self._client
