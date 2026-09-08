from fastapi import APIRouter

from app.api.routers import admin, auth, chat, conversations, system, web


router = APIRouter()
router.include_router(web.router)
router.include_router(system.router)
router.include_router(auth.router)
router.include_router(conversations.router)
router.include_router(chat.router)
router.include_router(admin.router)
