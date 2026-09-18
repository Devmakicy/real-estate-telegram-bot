import logging
import re
from types import SimpleNamespace

from aiogram import Bot
from aiogram.types import Message, User as TgUser
from aiogram.exceptions import TelegramBadRequest

from config import ADMIN_GROUP_ID, BOT_DISPLAY_NAME
from database.crud import get_user_by_telegram_id, get_user_by_topic_id, set_user_topic_id
from database.models import User
from database.session import async_session

logger = logging.getLogger(__name__)


def format_topic_name(tg_user: TgUser) -> str:
    name = tg_user.first_name or tg_user.username or "Клиент"
    name = name.strip()
    if re.fullmatch(r"[a-zA-Z]+", name):
        name = name.upper()
    return f"🔵 {name} ID {tg_user.id}"


async def get_or_create_topic(
    bot: Bot,
    tg_user: TgUser | None = None,
    *,
    telegram_id: int | None = None,
    username: str | None = None,
    first_name: str | None = None,
    last_name: str | None = None,
) -> int | None:
    if not ADMIN_GROUP_ID:
        return None

    if tg_user:
        telegram_id = tg_user.id
        username = tg_user.username
        first_name = tg_user.first_name
        last_name = tg_user.last_name

    if telegram_id is None:
        return None

    async with async_session() as session:
        user = await get_user_by_telegram_id(session, telegram_id)
        if user and user.topic_id:
            try:
                await bot.send_chat_action(
                    ADMIN_GROUP_ID,
                    "typing",
                    message_thread_id=user.topic_id,
                )
                return user.topic_id
            except TelegramBadRequest:
                logger.warning(
                    "Stale topic_id=%s for user %s, creating new",
                    user.topic_id,
                    telegram_id,
                )
                user.topic_id = None
                await session.commit()

        topic_name = format_topic_name(
            SimpleNamespace(
                id=telegram_id,
                first_name=first_name,
                username=username,
            )
        )
        try:
            topic = await bot.create_forum_topic(
                chat_id=ADMIN_GROUP_ID,
                name=topic_name[:128],
            )
            topic_id = topic.message_thread_id
        except TelegramBadRequest as e:
            logger.error("Cannot create forum topic: %s", e)
            return None

        if user:
            await set_user_topic_id(session, user.id, topic_id)
        else:
            from database.crud import get_or_create_user

            user = await get_or_create_user(
                session,
                telegram_id=telegram_id,
                username=username,
                first_name=first_name,
                last_name=last_name,
            )
            await set_user_topic_id(session, user.id, topic_id)

        header = (
            f"🆕 <b>Новый клиент</b>\n\n"
            f"👤 {first_name or ''} {last_name or ''}\n"
            f"Username: @{username or '—'}\n"
            f"ID: <code>{telegram_id}</code>\n"
            f"📂 {BOT_DISPLAY_NAME}\n\n"
            f"💬 Пишите в этот топик — клиент получит сообщение в боте."
        )
        try:
            await bot.send_message(
                ADMIN_GROUP_ID,
                header,
                message_thread_id=topic_id,
                parse_mode="HTML",
            )
        except TelegramBadRequest as e:
            logger.error("Cannot send topic header: %s", e)

        return topic_id


async def mirror_client_message(bot: Bot, message: Message) -> None:
    if not ADMIN_GROUP_ID or not message.from_user:
        return

    topic_id = await get_or_create_topic(bot, message.from_user)
    if not topic_id:
        logger.warning("Mirror skipped: no topic for user %s", message.from_user.id)
        return

    try:
        if message.text and message.text.startswith("/"):
            if message.text.split()[0] in ("/start",):
                return
            action = message.text.split()[0]
            labels = {
                "/help": "Клиент запросил помощь",
            }
            text = labels.get(action, f"Клиент отправил команду {action}")
            await bot.send_message(
                ADMIN_GROUP_ID,
                f"📩 {text}",
                message_thread_id=topic_id,
            )
            return

        if message.text and re.match(r"https?://", message.text.strip()):
            await bot.send_message(
                ADMIN_GROUP_ID,
                f"📩 Клиент отправил ссылку на объявление:\n{message.text.strip()}",
                message_thread_id=topic_id,
            )
            return

        if message.text in ("📋 Новая заявка", "📞 Мои заявки", "✅ Готово", "❌ Отмена"):
            await bot.send_message(
                ADMIN_GROUP_ID,
                f"📩 Клиент нажал «{message.text}»",
                message_thread_id=topic_id,
            )
            return

        if message.text:
            await bot.send_message(
                ADMIN_GROUP_ID,
                f"👤 <b>Клиент:</b>\n{message.text}",
                message_thread_id=topic_id,
                parse_mode="HTML",
            )
            return

        await bot.forward_message(
            chat_id=ADMIN_GROUP_ID,
            from_chat_id=message.chat.id,
            message_id=message.message_id,
            message_thread_id=topic_id,
        )
    except TelegramBadRequest as e:
        logger.warning("Mirror failed for user %s: %s", message.from_user.id, e)
        preview = message.text or message.caption or "[медиа]"
        await bot.send_message(
            ADMIN_GROUP_ID,
            f"📩 Клиент: {preview[:500]}",
            message_thread_id=topic_id,
        )


async def notify_topic(bot: Bot, user: User, text: str) -> None:
    if not ADMIN_GROUP_ID:
        return

    topic_id = user.topic_id
    if not topic_id:
        return

    try:
        await bot.send_message(
            ADMIN_GROUP_ID,
            text,
            message_thread_id=topic_id,
            parse_mode="HTML",
        )
    except TelegramBadRequest as e:
        logger.warning("Topic notify failed: %s", e)


async def _send_message_to_client(bot: Bot, client_id: int, message: Message) -> None:
    caption = message.caption

    if message.text:
        await bot.send_message(client_id, message.text)
        return
    if message.photo:
        await bot.send_photo(client_id, message.photo[-1].file_id, caption=caption)
        return
    if message.video:
        await bot.send_video(client_id, message.video.file_id, caption=caption)
        return
    if message.document:
        await bot.send_document(client_id, message.document.file_id, caption=caption)
        return
    if message.voice:
        await bot.send_voice(client_id, message.voice.file_id, caption=caption)
        return
    if message.audio:
        await bot.send_audio(client_id, message.audio.file_id, caption=caption)
        return
    if message.video_note:
        await bot.send_video_note(client_id, message.video_note.file_id)
        return
    if message.sticker:
        await bot.send_sticker(client_id, message.sticker.file_id)
        return
    if message.animation:
        await bot.send_animation(client_id, message.animation.file_id, caption=caption)
        return

    await bot.copy_message(
        chat_id=client_id,
        from_chat_id=message.chat.id,
        message_id=message.message_id,
    )


async def relay_admin_to_client(bot: Bot, message: Message) -> bool:
    if not ADMIN_GROUP_ID or message.chat.id != ADMIN_GROUP_ID:
        return False
    if not message.message_thread_id or not message.from_user:
        return False
    if message.message_thread_id == 1:
        return False
    if message.from_user.is_bot:
        return False
    if message.text and message.text.startswith("/"):
        return False

    async with async_session() as session:
        user = await get_user_by_topic_id(session, message.message_thread_id)
    if not user:
        return False

    try:
        await _send_message_to_client(bot, user.telegram_id, message)
        return True
    except TelegramBadRequest as e:
        logger.warning("Relay to client %s failed: %s", user.telegram_id, e)
        if message.text:
            await bot.send_message(user.telegram_id, message.text)
            return True
        if message.caption:
            await bot.send_message(user.telegram_id, message.caption)
            return True
        return False
