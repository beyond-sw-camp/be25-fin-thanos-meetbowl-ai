import asyncio
import json

import httpx
import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.ports.embedding import EmbeddingRequest
from app.providers.openai_embedding import OpenAIEmbeddingProvider


def test_openai_embedding_sends_configured_dimensions() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "model": "text-embedding-3-large",
                "data": [{"embedding": [0.1, 0.2, 0.3]}],
            },
        )

    async def scenario() -> None:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler)
        ) as client:
            provider = OpenAIEmbeddingProvider(
                api_key="test-key",
                base_url="https://api.openai.test/v1",
                model_name="text-embedding-3-large",
                dimensions=1536,
                client=client,
            )
            result = await provider.embed(
                EmbeddingRequest(
                    texts=["검색 질의"],
                    model_profile="query-embedding",
                )
            )
            assert result.model_name == "text-embedding-3-large"
            assert result.dimensions == 3

    asyncio.run(scenario())

    assert captured == {
        "input": ["검색 질의"],
        "model": "text-embedding-3-large",
        "encoding_format": "float",
        "dimensions": 1536,
    }


def test_settings_reject_mismatched_document_and_query_dimensions() -> None:
    with pytest.raises(ValidationError, match="provider/model/dimensions must match"):
        Settings(
            document_embedding_dimensions=1536,
            query_embedding_dimensions=1024,
        )
