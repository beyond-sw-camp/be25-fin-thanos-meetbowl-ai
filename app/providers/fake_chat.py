from app.ports.embedding_provider import EmbeddingProvider
from app.ports.reranker import Reranker
from app.rag.qdrant_chat import QdrantChatRetriever
from app.schemas.chat import ChatCommand, ChatResult


class FakeChatProvider:
    """Gemini 없이 동작하는 테스트용 챗봇 provider.

    embedding/retriever가 주입되면 실제 Qdrant 검색까지 수행하고,
    없으면 고정 답변만 돌려준다(통신 계약 검증용).
    """

    def __init__(
        self,
        model_name: str,
        prompt_version: str,
        embedding_provider: EmbeddingProvider | None = None,
        retriever: QdrantChatRetriever | None = None,
        reranker: Reranker | None = None,
        top_n: int = 10,
    ) -> None:
        self._model_name = model_name
        self._prompt_version = prompt_version
        self._embedding_provider = embedding_provider
        self._retriever = retriever
        self._reranker = reranker
        self._top_n = top_n

    async def answer(self, command: ChatCommand) -> ChatResult:
        """질문을 임베딩해 권한 범위 내 자료를 검색하고 결과를 요약한다."""
        # RAG 구성 요소가 주입된 경우에만 실제 검색을 수행한다.
        if self._embedding_provider is not None and self._retriever is not None:
            vector = await self._embedding_provider.embed(command.question)
            sources = await self._retriever.search(
                vector=vector, query=command.question, command=command
            )
            if self._reranker is not None:
                sources = await self._reranker.rerank(
                    query=command.question, sources=sources, top_n=self._top_n
                )
            if sources:
                # LLM 생성 대신 검색된 snippet을 이어 붙여 결정적으로 요약한다.
                summary = " ".join(source.snippet for source in sources)
                return ChatResult(
                    answer=f"검색된 자료를 요약하면 다음과 같습니다. {summary}",
                    sources=sources,
                    model=self._model_name,
                    prompt_version=self._prompt_version,
                )
        return ChatResult(
            answer="검색 가능한 자료에서 질문의 근거를 확인하지 못했습니다.",
            sources=[],
            model=self._model_name,
            prompt_version=self._prompt_version,
        )
