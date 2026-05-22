from fastapi import FastAPI

from app.api.v1.router import router as api_v1_router


def create_app() -> FastAPI:
    app = FastAPI(
        title="Meetbowl AI API",
        version="0.1.0",
    )
    app.include_router(api_v1_router, prefix="/api/v1")
    return app


app = create_app()
