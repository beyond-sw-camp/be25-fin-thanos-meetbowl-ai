from app.ports.embedding_provider import EmbeddingProvider
from app.rag.chunking import DEFAULT_MAX_CHARS, DEFAULT_OVERLAP_CHARS, chunk_text
from app.rag.qdrant_index import QdrantDocumentIndexer
from app.schemas.indexing import IndexDocumentCommand, IndexDocumentResult


class DocumentIndexingWorkflow:
    """본문을 청크로 나눠 임베딩하고 Qdrant에 색인하는 문서 색인 workflow."""

    def __init__(
        self,
        *,
        embedding_provider: EmbeddingProvider,
        indexer: QdrantDocumentIndexer,
        chunk_max_chars: int = DEFAULT_MAX_CHARS,
        chunk_overlap_chars: int = DEFAULT_OVERLAP_CHARS,
    ) -> None:
        self._embedding_provider = embedding_provider
        self._indexer = indexer
        self._chunk_max_chars = chunk_max_chars
        self._chunk_overlap_chars = chunk_overlap_chars

    async def execute(self, command: IndexDocumentCommand) -> IndexDocumentResult:
        """본문을 청크로 분할해 각 청크를 임베딩한 뒤 Qdrant에 색인한다."""
        chunks = chunk_text(
            command.content,
            max_chars=self._chunk_max_chars,
            overlap_chars=self._chunk_overlap_chars,
        )
        # content는 min_length=1이라 비지 않지만, 공백뿐인 경우 대비 fallback.
        if not chunks:
            chunks = [command.content]

        # 청크마다 제목 문맥을 함께 임베딩해 검색 시 제목 정보도 반영되게 한다.
        chunk_vectors = [
            (chunk, await self._embedding_provider.embed(f"{command.title}\n{chunk}"))
            for chunk in chunks
        ]
        await self._indexer.upsert_document(command=command, chunks=chunk_vectors)
        return IndexDocumentResult(
            document_id=command.document_id,
            indexed_chunks=len(chunk_vectors),
            collection=self._indexer.collection,
        )
