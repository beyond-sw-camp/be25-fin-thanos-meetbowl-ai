import httpx

from app.core.errors import DocumentIndexFailedError
from app.ports.vector_store import ReplaceDocumentRequest
from app.rag.sparse import SparseEncoder

# 권한·유형 필터에 쓰는 payload 필드. 대규모 포인트에서 인덱스 없이 필터하면 풀스캔이 되므로
# keyword 인덱스를 만들어 검색 시 후보 pool을 인덱스로 좁힌다.
_FILTERED_PAYLOAD_FIELDS = (
    "ownerUserId",
    "workspaceId",
    "sharedWorkspaceIds",
    "sourceType",
)


class QdrantVectorStore:
    def __init__(
        self,
        *,
        base_url: str,
        collection_name: str,
        client: httpx.AsyncClient | None = None,
        sparse_encoder: SparseEncoder | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._collection_name = collection_name
        self._client = client or httpx.AsyncClient(timeout=10.0)
        self._owns_client = client is None
        self._ensured_dimensions: int | None = None
        self._sparse_encoder = sparse_encoder or SparseEncoder()

    async def replace_document(self, request: ReplaceDocumentRequest) -> None:
        if not request.points:
            raise DocumentIndexFailedError("저장할 벡터 포인트가 없습니다.", retryable=False)
        await self._ensure_collection(request.vector_size)
        # sourceId 기준 전체 교체 전략을 사용한다.
        # 승인 후 수정/재승인으로 같은 문서가 다시 색인될 때 이전 chunk 잔재를 남기지 않는다.
        await self._delete_document_points(request.document_id)
        await self._upsert_points(request)

    async def delete_document(self, document_id: str) -> None:
        # 문서가 삭제되면 챗봇 검색에 다시 나오지 않도록 해당 문서의 모든 chunk 포인트를 제거한다.
        # collection이 아직 없을 수도 있으므로(첫 색인 전 삭제 등) 없으면 조용히 통과한다.
        await self._delete_document_points(document_id)

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def _ensure_collection(self, vector_size: int) -> None:
        if self._ensured_dimensions == vector_size:
            return
        response = await self._request(
            "GET", f"/collections/{self._collection_name}", retryable_not_found=False
        )
        if response.status_code == 404:
            # 로컬 개발과 첫 기동 시에는 collection이 없을 수 있으므로 자동 생성한다.
            create_response = await self._request(
                "PUT",
                f"/collections/{self._collection_name}",
                json={
                    "vectors": {"dense": {"size": vector_size, "distance": "Cosine"}},
                    "sparse_vectors": {"sparse": {"modifier": "idf"}},
                },
            )
            if create_response.status_code not in (200, 201):
                raise DocumentIndexFailedError("Qdrant collection 생성에 실패했습니다.")
        else:
            payload = response.json().get("result", {})
            current_size = (
                payload.get("config", {})
                .get("params", {})
                .get("vectors", {})
                .get("dense", {})
                .get("size")
            )
            if current_size is not None and current_size != vector_size:
                # 임베딩 모델 차원과 collection 차원이 다르면 저장 데이터를 복구할 수 없으므로
                # 재시도 대신 운영 설정 오류로 취급한다.
                raise DocumentIndexFailedError(
                    "Qdrant collection vector dimension이 현재 설정과 다릅니다.",
                    retryable=False,
                )
        await self._ensure_payload_indexes()
        self._ensured_dimensions = vector_size

    async def _ensure_payload_indexes(self) -> None:
        # 필터 필드별 keyword 인덱스를 보장한다. 이미 있으면 Qdrant가 멱등 처리하므로 매번 호출해도 안전하다.
        for field_name in _FILTERED_PAYLOAD_FIELDS:
            await self._request(
                "PUT",
                f"/collections/{self._collection_name}/index",
                params={"wait": "true"},
                json={"field_name": field_name, "field_schema": "keyword"},
            )

    async def _delete_document_points(self, document_id: str) -> None:
        response = await self._request(
            "POST",
            f"/collections/{self._collection_name}/points/delete",
            params={"wait": "true"},
            json={
                "filter": {
                    "must": [
                        {"key": "sourceId", "match": {"value": document_id}},
                    ]
                }
            },
        )
        if response.status_code != 200:
            raise DocumentIndexFailedError("기존 문서 벡터 삭제에 실패했습니다.")

    async def _upsert_points(self, request: ReplaceDocumentRequest) -> None:
        response = await self._request(
            "PUT",
            f"/collections/{self._collection_name}/points",
            params={"wait": "true"},
            json={
                "points": [
                    {
                        "id": point.point_id,
                        "vector": {
                            "dense": point.vector,
                            "sparse": self._sparse_encoder.encode(
                                str(point.payload.get("content", ""))
                            ),
                        },
                        "payload": point.payload,
                    }
                    for point in request.points
                ]
            },
        )
        if response.status_code != 200:
            raise DocumentIndexFailedError("문서 벡터 저장에 실패했습니다.")

    async def _request(
        self,
        method: str,
        path: str,
        *,
        retryable_not_found: bool = True,
        **kwargs: object,
    ) -> httpx.Response:
        try:
            response = await self._client.request(
                method,
                f"{self._base_url}{path}",
                **kwargs,
            )
        except httpx.HTTPError as exc:
            raise DocumentIndexFailedError("Qdrant 요청에 실패했습니다.") from exc
        if response.status_code == 404 and not retryable_not_found:
            return response
        if response.status_code >= 500:
            raise DocumentIndexFailedError("Qdrant 서버 오류가 발생했습니다.")
        if response.status_code >= 400 and response.status_code != 404:
            raise DocumentIndexFailedError(
                f"Qdrant 요청이 실패했습니다. status={response.status_code}",
                retryable=False,
            )
        return response
