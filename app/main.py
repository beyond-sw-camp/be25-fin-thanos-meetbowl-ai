from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.v1.router import router as api_v1_router
from app.consumers.redis_feedback import FeedbackEventProcessor, RedisFeedbackRuntime
from app.container import Container, build_container
from app.core.config import Settings, get_settings
from app.core.errors import AiError
from app.events.rabbit import RabbitRuntime
from app.schemas.api import ErrorBody, FailureResponse


def create_app(
    *, settings: Settings | None = None, container: Container | None = None
) -> FastAPI:
    resolved_settings = settings or get_settings()
    resolved_container = container or build_container(resolved_settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.settings = resolved_settings
        app.state.container = resolved_container
        rabbit_runtime: RabbitRuntime | None = None
        redis_feedback_runtime: RedisFeedbackRuntime | None = None
        if resolved_settings.rabbitmq_enabled:
            rabbit_runtime = RabbitRuntime(
                resolved_settings,
                resolved_container.minutes_workflow,
                resolved_container.document_indexing_workflow,
            )
            await rabbit_runtime.start()
        if resolved_settings.redis_feedback_enabled:
            processor = FeedbackEventProcessor(
                workflow=resolved_container.meeting_feedback_workflow,
                publisher=None,
                max_segments=resolved_settings.feedback_window_max_segments,
                max_window_seconds=resolved_settings.feedback_window_max_seconds,
                min_segments=resolved_settings.feedback_min_segments,
                min_window_chars=resolved_settings.feedback_min_window_chars,
                trigger_interval_seconds=resolved_settings.feedback_trigger_interval_seconds,
                cooldown_seconds=resolved_settings.feedback_cooldown_seconds,
            )
            redis_feedback_runtime = RedisFeedbackRuntime(
                redis_url=resolved_settings.redis_url,
                consumer_group=resolved_settings.redis_feedback_consumer_group,
                consumer_name=resolved_settings.redis_feedback_consumer_name,
                stream_max_length=resolved_settings.redis_feedback_stream_max_length,
                scan_interval_seconds=resolved_settings.redis_feedback_scan_interval_seconds,
                processor=processor,
            )
            processor.set_publisher(redis_feedback_runtime)
            await redis_feedback_runtime.start()
        yield
        if rabbit_runtime is not None:
            await rabbit_runtime.stop()
        if redis_feedback_runtime is not None:
            await redis_feedback_runtime.stop()
        await resolved_container.qdrant_vector_store.aclose()

    app = FastAPI(
        title="Meetbowl AI API",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.settings = resolved_settings
    app.state.container = resolved_container
    app.include_router(api_v1_router, prefix="/api/v1")

    @app.exception_handler(AiError)
    async def handle_ai_error(request: Request, exc: AiError) -> JSONResponse:
        del request
        body = FailureResponse(error=ErrorBody(code=exc.code, message=exc.message))
        return JSONResponse(
            status_code=exc.status_code,
            content=body.model_dump(mode="json", by_alias=True),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        del request
        details = [
            {
                "field": ".".join(str(part) for part in error["loc"][1:]),
                "reason": error["msg"],
            }
            for error in exc.errors()
        ]
        body = FailureResponse(
            error=ErrorBody(
                code="VALIDATION_FAILED",
                message="요청 값이 올바르지 않습니다.",
                details=details,
            )
        )
        return JSONResponse(status_code=422, content=body.model_dump(mode="json", by_alias=True))

    return app


app = create_app()
