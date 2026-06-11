from fastapi import APIRouter

from app.api.v1.routes import chat, health, minutes

router = APIRouter()
router.include_router(health.router)
router.include_router(minutes.router)
router.include_router(chat.router)
