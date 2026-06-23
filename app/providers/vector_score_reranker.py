from app.schemas.chat import ChatSource
from app.rag.source_merge import merge_chat_sources


class VectorScoreReranker:
    """검색 점수로 정렬하고 같은 문서의 관련 청크를 하나의 소스로 합치는 reranker.

    LLM을 호출하지 않으므로 검색마다 들던 Gemini 호출과 그에 따른 과부하(503) 위험을 없앤다.
    문서별 가장 점수가 높은 청크의 순위를 유지하면서 후속 청크 본문도 합쳐,
    한 파일이 top_n을 독점하지 않고 문서 내 근거도 손실하지 않게 한다.
    """

    def __init__(self, score_threshold: float = 0.0) -> None:
        # 관련도가 이 값 미만인 후보는 버린다. 0.0이면 무근거 차단 비활성(전부 통과).
        self._score_threshold = score_threshold

    async def rerank(
        self, *, query: str, sources: list[ChatSource], top_n: int
    ) -> list[ChatSource]:
        """임계값 통과 후 resource_id별 청크를 합쳐 상위 top_n개 문서를 반환한다."""
        ordered = sorted(sources, key=lambda source: source.score, reverse=True)
        kept = [source for source in ordered if source.score >= self._score_threshold]
        diversified: list[ChatSource] = []
        index_by_resource_id = {}
        for source in kept:
            existing_index = index_by_resource_id.get(source.resource_id)
            if existing_index is not None:
                diversified[existing_index] = merge_chat_sources(
                    diversified[existing_index], source
                )
                continue
            index_by_resource_id[source.resource_id] = len(diversified)
            diversified.append(source)
        return diversified[:top_n]
