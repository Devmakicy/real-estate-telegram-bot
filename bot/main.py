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
        raise ValueError(
            "BOT_TOKEN is not set. "
            "Locally: copy .env.example to .env. "
            "On Railway: Service → Variables → add BOT_TOKEN."
        )

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

    await init_db()

    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())
    dp.message.middleware(MirrorMiddleware())
    dp.include_router(setup_routers())

    await set_bot_description(bot)
    await validate_setup(bot)

    logger.info("Bot started")
    await dp.start_polling(bot)


async def validate_setup(bot: Bot) -> None:
    if not ADMIN_GROUP_ID:
        logger.error(
            "ADMIN_GROUP_ID not set! Topics disabled. "
            "Add ADMIN_GROUP_ID=-1004338467125 to Railway Variables."
        )
        return
    try:
        chat = await bot.get_chat(ADMIN_GROUP_ID)
        me = await bot.get_me()
        member = await bot.get_chat_member(ADMIN_GROUP_ID, me.id)
        logger.info(
            "Admin group OK: %s | forum=%s | bot=%s",
            chat.title,
            getattr(chat, "is_forum", False),
            member.status,
        )
    except Exception as e:
        logger.error("Cannot access admin group %s: %s", ADMIN_GROUP_ID, e)


if __name__ == "__main__":
    asyncio.run(main())
