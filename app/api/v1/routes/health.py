from __future__ import annotations

import aio_pika
import httpx
from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse
from redis.asyncio import Redis

from app.core.config import Settings

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/ready")
async def readiness_check(request: Request) -> JSONResponse:
    settings: Settings = request.app.state.settings
    qdrant_status = await _check_qdrant_status(settings)

    redis_required = _is_redis_required(settings)
    redis_status = (
        await _check_redis_status(settings)
        if redis_required
        else {"status": "disabled"}
    )

    rabbitmq_status = (
        await _check_rabbitmq_status(settings)
        if settings.rabbitmq_enabled
        else {"status": "disabled"}
    )

    ok = (
        qdrant_status["status"] == "ok"
        and (not redis_required or redis_status["status"] == "ok")
        and (not settings.rabbitmq_enabled or rabbitmq_status["status"] == "ok")
    )

    body = {
        "status": "ok" if ok else "degraded",
        "checks": {
            "qdrant": qdrant_status,
            "redis": redis_status,
            "rabbitmq": rabbitmq_status,
        },
    }
    return JSONResponse(
        status_code=status.HTTP_200_OK if ok else status.HTTP_503_SERVICE_UNAVAILABLE,
        content=body,
    )


@router.get("/health/vector-store")
async def vector_store_health(request: Request) -> JSONResponse:
    settings: Settings = request.app.state.settings
    qdrant_status = await _check_qdrant_status(settings)
    ok = qdrant_status["status"] == "ok"
    return JSONResponse(
        status_code=status.HTTP_200_OK if ok else status.HTTP_503_SERVICE_UNAVAILABLE,
        content=qdrant_status,
    )


def _is_redis_required(settings: Settings) -> bool:
    return settings.rabbitmq_enabled or settings.redis_feedback_enabled


async def _check_qdrant_status(settings: Settings) -> dict[str, str]:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{settings.qdrant_url.rstrip('/')}/collections")
        if response.status_code < 400:
            return {"status": "ok"}
        return {
            "status": "error",
            "reason": f"unexpected_status:{response.status_code}",
        }
    except httpx.HTTPError as exc:
        return {"status": "error", "reason": exc.__class__.__name__}


async def _check_redis_status(settings: Settings) -> dict[str, str]:
    client = Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        if await client.ping():
            return {"status": "ok"}
        return {"status": "error", "reason": "ping_failed"}
    except Exception as exc:
        return {"status": "error", "reason": exc.__class__.__name__}
    finally:
        await client.aclose()


async def _check_rabbitmq_status(settings: Settings) -> dict[str, str]:
    connection: aio_pika.abc.AbstractRobustConnection | None = None
    try:
        connection = await aio_pika.connect_robust(
            settings.rabbitmq_connection_url(),
            timeout=5.0,
        )
        return {"status": "ok"}
    except Exception as exc:
        return {"status": "error", "reason": exc.__class__.__name__}
    finally:
        if connection is not None:
            await connection.close()
