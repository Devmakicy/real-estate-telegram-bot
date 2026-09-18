from aiogram import Router

from bot.handlers.admin import router as admin_router
from bot.handlers.client import router as client_router
from bot.handlers.group_admin import router as group_admin_router
from config import ADMIN_GROUP_ID


def setup_routers() -> Router:
    root = Router()
    if ADMIN_GROUP_ID:
        root.include_router(group_admin_router)
    root.include_router(admin_router)
    root.include_router(client_router)
    return root
