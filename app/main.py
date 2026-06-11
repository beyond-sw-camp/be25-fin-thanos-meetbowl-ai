from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.v1.router import router as api_v1_router
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
        app.state.container = resolved_container
        rabbit_runtime: RabbitRuntime | None = None
        if resolved_settings.rabbitmq_enabled:
            rabbit_runtime = RabbitRuntime(
                resolved_settings, resolved_container.minutes_workflow
            )
            await rabbit_runtime.start()
        yield
        if rabbit_runtime is not None:
            await rabbit_runtime.stop()

    app = FastAPI(
        title="Meetbowl AI API",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.container = resolved_container
    app.state.settings = resolved_settings
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
