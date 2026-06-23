import asyncio

from app.ports.embedding_provider import EmbeddingProvider
from app.ports.reranker import Reranker
from app.rag.qdrant_chat import QdrantChatRetriever
from app.rag.source_merge import merge_chat_sources
from app.schemas.chat import ChatCommand, ChatSource, ChatSourceType


async def search_queries_in_parallel(
    *,
    queries: list[str],
    command: ChatCommand,
    embedding_provider: EmbeddingProvider,
    retriever: QdrantChatRetriever,
    reranker: Reranker,
    source_types: list[ChatSourceType] | None,
    candidate_pool: int,
    top_n: int,
) -> list[ChatSource]:
    """질의별 임베딩·Qdrant 검색을 병렬 실행하고 순위별로 공정하게 합친다.

    각 질의의 1위부터 round-robin으로 합쳐 한 주제가 결과를 독점하지 않게 하고,
    resource_id 기준으로 중복 문서를 제거한다.
    """

    async def search_one(query: str) -> list[ChatSource]:
        vector = await embedding_provider.embed(query)
        candidates = await retriever.search(
            vector=vector,
            query=query,
            command=command,
            source_types=source_types,
            limit=candidate_pool,
        )
        return await reranker.rerank(query=query, sources=candidates, top_n=top_n)

    ranked_by_query = await asyncio.gather(*(search_one(query) for query in queries))
    merged: list[ChatSource] = []
    index_by_resource_id = {}
    for rank in range(top_n):
        for ranked in ranked_by_query:
            if rank >= len(ranked):
                continue
            source = ranked[rank]
            existing_index = index_by_resource_id.get(source.resource_id)
            if existing_index is not None:
                merged[existing_index] = merge_chat_sources(
                    merged[existing_index], source
                )
                continue
            if len(merged) == top_n:
                continue
            index_by_resource_id[source.resource_id] = len(merged)
            merged.append(source)
    return merged
