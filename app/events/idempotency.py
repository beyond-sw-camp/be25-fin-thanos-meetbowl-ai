from uuid import UUID

from redis.asyncio import Redis


class InMemoryEventTracker:
    def __init__(self) -> None:
        self._completed: set[UUID] = set()
        self._retry_counts: dict[UUID, int] = {}

    def is_completed(self, event_id: UUID) -> bool:
        return event_id in self._completed

    def mark_completed(self, event_id: UUID) -> None:
        self._completed.add(event_id)
        self._retry_counts.pop(event_id, None)

    def increment_retry(self, event_id: UUID) -> int:
        count = self._retry_counts.get(event_id, 0) + 1
        self._retry_counts[event_id] = count
        return count


class RedisEventTracker:
    """Persist consumer completion and retry state across AI server restarts."""

    def __init__(self, redis: Redis, *, namespace: str, ttl_seconds: int) -> None:
        self._redis = redis
        self._namespace = namespace
        self._ttl_seconds = ttl_seconds

    async def is_completed(self, event_id: UUID) -> bool:
        return bool(await self._redis.exists(self._completed_key(event_id)))

    async def mark_completed(self, event_id: UUID) -> None:
        await self._redis.set(self._completed_key(event_id), "1", ex=self._ttl_seconds)
        await self._redis.delete(self._retry_key(event_id))

    async def increment_retry(self, event_id: UUID) -> int:
        key = self._retry_key(event_id)
        count = int(await self._redis.incr(key))
        if count == 1:
            await self._redis.expire(key, self._ttl_seconds)
        return count

    def _completed_key(self, event_id: UUID) -> str:
        return f"{self._namespace}:completed:{event_id}"

    def _retry_key(self, event_id: UUID) -> str:
        return f"{self._namespace}:retry:{event_id}"
