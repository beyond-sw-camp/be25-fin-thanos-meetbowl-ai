import asyncio
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from typing import Generic, TypeVar

T = TypeVar("T")


class AsyncResultCache(Generic[T]):
    """문자열 키 기반 async 결과 캐시(LRU + 선택적 TTL).

    같은 질의에 대한 비싼 호출(질의 확장 LLM, 임베딩)을 요청 내·요청 간 재사용한다.
    같은 키가 동시에 들어와도 한 번만 계산하도록 키별 락으로 stampede를 막는다.
    """

    def __init__(self, *, max_size: int = 512, ttl_seconds: float | None = None) -> None:
        self._max_size = max_size
        self._ttl = ttl_seconds
        self._store: OrderedDict[str, tuple[float, T]] = OrderedDict()
        self._key_locks: dict[str, asyncio.Lock] = {}
        self._guard = asyncio.Lock()

    async def get_or_compute(self, key: str, compute: Callable[[], Awaitable[T]]) -> T:
        hit = self._lookup(key)
        if hit is not None:
            return hit
        # 같은 키 동시 요청은 한 번만 계산한다.
        async with self._guard:
            key_lock = self._key_locks.setdefault(key, asyncio.Lock())
        async with key_lock:
            hit = self._lookup(key)
            if hit is not None:
                return hit
            value = await compute()
            self._insert(key, value)
            return value

    def _lookup(self, key: str) -> T | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        stored_at, value = entry
        if self._ttl is not None and time.monotonic() - stored_at > self._ttl:
            self._store.pop(key, None)
            return None
        self._store.move_to_end(key)
        return value

    def _insert(self, key: str, value: T) -> None:
        self._store[key] = (time.monotonic(), value)
        self._store.move_to_end(key)
        while len(self._store) > self._max_size:
            evicted, _ = self._store.popitem(last=False)
            self._key_locks.pop(evicted, None)
