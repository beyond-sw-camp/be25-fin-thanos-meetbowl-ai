import asyncio
import json

import httpx
import pytest

from app.core.errors import DocumentIndexFailedError, ProviderUnavailableError
from app.ports.embedding import EmbeddingRequest
from app.providers.openai_embedding import OpenAIEmbeddingProvider


def test_openai_embedding_provider_calls_embeddings_endpoint() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("Authorization")
        captured["body"] = json.loads(request.content.decode())
        return httpx.Response(
            200,
            json={
                "data": [
                    {"embedding": [0.1, 0.2, 0.3]},
                    {"embedding": [0.4, 0.5, 0.6]},
                ],
                "model": "text-embedding-3-large",
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = OpenAIEmbeddingProvider(
        api_key="test-key",
        base_url="https://api.openai.com/v1",
        model_name="text-embedding-3-large",
        client=client,
    )

    result = asyncio.run(
        provider.embed(
            EmbeddingRequest(
                texts=["first text", "second text"],
                model_profile="document-embedding",
            )
        )
    )

    assert captured["url"] == "https://api.openai.com/v1/embeddings"
    assert captured["auth"] == "Bearer test-key"
    assert captured["body"] == {
        "input": ["first text", "second text"],
        "model": "text-embedding-3-large",
        "encoding_format": "float",
    }
    assert result.model_name == "text-embedding-3-large"
    assert result.dimensions == 3

    asyncio.run(client.aclose())


def test_openai_embedding_provider_requires_api_key() -> None:
    provider = OpenAIEmbeddingProvider(
        api_key=None,
        base_url="https://api.openai.com/v1",
        model_name="text-embedding-3-large",
    )

    with pytest.raises(ProviderUnavailableError, match="OPENAI_API_KEY"):
        asyncio.run(
            provider.embed(
                EmbeddingRequest(
                    texts=["text"],
                    model_profile="document-embedding",
                )
            )
        )


def test_openai_embedding_provider_rejects_client_errors() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": {"message": "bad request"}})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = OpenAIEmbeddingProvider(
        api_key="test-key",
        base_url="https://api.openai.com/v1",
        model_name="text-embedding-3-large",
        client=client,
    )

    with pytest.raises(DocumentIndexFailedError, match="status=400"):
        asyncio.run(
            provider.embed(
                EmbeddingRequest(
                    texts=["text"],
                    model_profile="document-embedding",
                )
            )
        )

    asyncio.run(client.aclose())
