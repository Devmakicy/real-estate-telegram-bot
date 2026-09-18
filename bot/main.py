import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from bot.handlers import setup_routers
from bot.middlewares.mirror import MirrorMiddleware
from config import ADMIN_GROUP_ID, BOT_DESCRIPTION, BOT_TOKEN, DATA_DIR, UPLOADS_DIR
from database import init_db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def set_bot_description(bot: Bot) -> None:
    try:
        await bot.set_my_description(description=BOT_DESCRIPTION)
        await bot.set_my_short_description(short_description=BOT_DESCRIPTION[:120])
    except Exception as e:
        logger.warning("Could not set bot description: %s", e)


async def main() -> None:
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN is not set. Copy .env.example to .env and fill it in.")

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

    await init_db()

    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())
    if ADMIN_GROUP_ID:
        dp.message.middleware(MirrorMiddleware())
    dp.include_router(setup_routers())

    await set_bot_description(bot)

    logger.info("Bot started")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
