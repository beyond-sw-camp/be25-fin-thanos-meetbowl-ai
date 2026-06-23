"""질의 캐시: 적중 시 재계산 생략, TTL 만료, 동시 동일 키 단일 계산 검증."""

import asyncio

from app.core.cache import AsyncResultCache


def test_hit_avoids_recompute() -> None:
    calls = {"n": 0}

    async def compute() -> str:
        calls["n"] += 1
        return "value"

    cache: AsyncResultCache[str] = AsyncResultCache()

    async def run() -> None:
        assert await cache.get_or_compute("k", compute) == "value"
        assert await cache.get_or_compute("k", compute) == "value"

    asyncio.run(run())
    assert calls["n"] == 1


def test_ttl_expiry_recomputes() -> None:
    calls = {"n": 0}

    async def compute() -> int:
        calls["n"] += 1
        return calls["n"]

    cache: AsyncResultCache[int] = AsyncResultCache(ttl_seconds=0.05)

    async def run() -> None:
        assert await cache.get_or_compute("k", compute) == 1
        await asyncio.sleep(0.08)
        assert await cache.get_or_compute("k", compute) == 2

    asyncio.run(run())
    assert calls["n"] == 2


def test_lru_eviction() -> None:
    cache: AsyncResultCache[str] = AsyncResultCache(max_size=2)

    async def run() -> None:
        await cache.get_or_compute("a", lambda: _const("A"))
        await cache.get_or_compute("b", lambda: _const("B"))
        await cache.get_or_compute("c", lambda: _const("C"))  # a 축출
        recomputed = {"a": 0}

        async def compute_a() -> str:
            recomputed["a"] += 1
            return "A2"

        # a는 축출됐으므로 재계산된다.
        assert await cache.get_or_compute("a", compute_a) == "A2"
        assert recomputed["a"] == 1

    asyncio.run(run())


def test_concurrent_same_key_computes_once() -> None:
    calls = {"n": 0}

    async def compute() -> str:
        calls["n"] += 1
        await asyncio.sleep(0.02)
        return "v"

    cache: AsyncResultCache[str] = AsyncResultCache()

    async def run() -> None:
        results = await asyncio.gather(
            *(cache.get_or_compute("k", compute) for _ in range(5))
        )
        assert results == ["v"] * 5

    asyncio.run(run())
    assert calls["n"] == 1


async def _const(value: str) -> str:
    return value
