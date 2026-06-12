from fastapi import APIRouter

from app.api.v1.routes import chat, health, indexes, minutes

router = APIRouter()
router.include_router(health.router)
router.include_router(minutes.router)
router.include_router(chat.router)
router.include_router(indexes.router)
