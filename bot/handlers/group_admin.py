from aiogram import F, Router
from aiogram.types import Message

from bot.services.topics import relay_admin_to_client
from config import ADMIN_GROUP_ID

router = Router()


@router.message(F.chat.id == ADMIN_GROUP_ID, F.message_thread_id)
async def admin_group_reply(message: Message) -> None:
    if not message.message_thread_id:
        return
    sent = await relay_admin_to_client(message.bot, message)
    if sent:
        try:
            await message.react([{"type": "emoji", "emoji": "✅"}])
        except Exception:
            pass
