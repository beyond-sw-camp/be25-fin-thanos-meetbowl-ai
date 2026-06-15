import asyncio
from typing import Any

from app.core.errors import ProviderUnavailableError


class S3FileStorage:
    """boto3로 S3(로컬은 LocalStack)에서 파일 바이너리를 다운로드한다.

    동기 boto3 호출을 asyncio.to_thread로 감싸 이벤트 루프를 막지 않는다.
    """

    def __init__(
        self,
        *,
        bucket: str,
        region: str,
        endpoint_url: str | None = None,
        access_key_id: str | None = None,
        secret_access_key: str | None = None,
        client: Any | None = None,
    ) -> None:
        self._bucket = bucket
        self._region = region
        self._endpoint_url = endpoint_url
        self._access_key_id = access_key_id
        self._secret_access_key = secret_access_key
        self._client = client

    async def download(self, storage_key: str) -> bytes:
        try:
            return await asyncio.to_thread(self._download_sync, storage_key)
        except Exception as exc:
            raise ProviderUnavailableError(
                f"S3에서 파일을 다운로드하지 못했습니다: {storage_key}"
            ) from exc

    def _download_sync(self, storage_key: str) -> bytes:
        response = self._get_client().get_object(Bucket=self._bucket, Key=storage_key)
        return response["Body"].read()

    def _get_client(self) -> Any:
        if self._client is None:
            import boto3

            self._client = boto3.client(
                "s3",
                region_name=self._region,
                endpoint_url=self._endpoint_url,
                aws_access_key_id=self._access_key_id,
                aws_secret_access_key=self._secret_access_key,
            )
        return self._client
