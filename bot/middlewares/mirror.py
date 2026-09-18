import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware, Bot
from aiogram.types import Message, TelegramObject

from bot.services.topics import mirror_client_message

logger = logging.getLogger(__name__)


class MirrorMiddleware(BaseMiddleware):
    """Зеркалит все сообщения клиента в топик — до и независимо от обработчиков."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if isinstance(event, Message):
            if (
                event.chat.type == "private"
                and event.from_user
                and not event.from_user.is_bot
            ):
                bot: Bot = data["bot"]
                try:
                    await mirror_client_message(bot, event)
                except Exception as e:
                    logger.error("Mirror error: %s", e)

        return await handler(event, data)
