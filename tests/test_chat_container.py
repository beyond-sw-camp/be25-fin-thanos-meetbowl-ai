"""챗봇 컨테이너 wiring 검증."""

from app.container import build_container
from app.core.config import Settings
from app.providers.fake_chat import FakeChatProvider
from app.providers.fake_reranker import FakeReranker
from app.rag.qdrant_chat import QdrantChatRetriever


def test_fake_chat_rag_mode_wires_retriever_dependencies() -> None:
    settings = Settings(
        chatbot_provider="fake",
        document_embedding_provider="fake",
        query_embedding_provider="fake",
        fake_chat_rag_enabled=True,
        qdrant_collection="test-chat-rag",
    )

    container = build_container(settings)
    provider = container.chat_workflow._provider

    assert isinstance(provider, FakeChatProvider)
    assert provider._embedding_provider is not None
    assert isinstance(provider._retriever, QdrantChatRetriever)
    assert isinstance(provider._reranker, FakeReranker)


def test_fake_chat_without_rag_keeps_plain_contract_mode() -> None:
    settings = Settings(
        chatbot_provider="fake",
        document_embedding_provider="fake",
        query_embedding_provider="fake",
        fake_chat_rag_enabled=False,
    )

    container = build_container(settings)
    provider = container.chat_workflow._provider

    assert isinstance(provider, FakeChatProvider)
    assert provider._embedding_provider is None
    assert provider._retriever is None
    assert provider._reranker is None
