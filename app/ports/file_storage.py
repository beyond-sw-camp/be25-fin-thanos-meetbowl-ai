from typing import Protocol


class FileStoragePort(Protocol):
    """드라이브 파일 바이너리를 저장소(S3)에서 가져오는 포트."""

    async def download(self, storage_key: str) -> bytes: ...
