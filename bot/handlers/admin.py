from aiogram import Bot, Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.services.topics import get_or_create_topic, notify_topic
from config import ADMIN_GROUP_ID, ADMIN_IDS
from database.crud import get_order, get_orders, get_user_by_telegram_id, update_order_status
from database.models import OrderStatus
from database.session import async_session

router = Router()

STATUS_LABELS = {
    OrderStatus.NEW.value: "🆕 Новая",
    OrderStatus.IN_PROGRESS.value: "⏳ В работе",
    OrderStatus.COMPLETED.value: "✅ Готово",
    OrderStatus.CANCELLED.value: "❌ Отменена",
}


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


async def notify_admins_new_order(bot: Bot, order_id: int) -> None:
    async with async_session() as session:
        order = await get_order(session, order_id)
    if not order:
        return

    user = order.user
    username = f"@{user.username}" if user.username else "—"
    name = " ".join(filter(None, [user.first_name, user.last_name])) or "—"

    text = (
        f"📋 <b>Новая заявка #{order.id}</b>\n\n"
        f"👤 {name} ({username})\n"
        f"🆔 <code>{user.telegram_id}</code>\n"
    )
    if order.link:
        text += f"\n🔗 {order.link}"
    if order.text:
        text += f"\n\n📝 {order.text}"
    text += f"\n\n📷 Фото: {len(order.photos)} шт."

    if ADMIN_GROUP_ID:
        if not user.topic_id:
            await get_or_create_topic(
                bot,
                telegram_id=user.telegram_id,
                username=user.username,
                first_name=user.first_name or "Клиент",
                last_name=user.last_name,
            )
            async with async_session() as session:
                refreshed = await get_order(session, order_id)
                user = refreshed.user if refreshed else user

        if user.topic_id:
            await notify_topic(bot, user, text)
            for photo in order.photos[:10]:
                try:
                    await bot.send_photo(
                        ADMIN_GROUP_ID,
                        photo.file_id,
                        message_thread_id=user.topic_id,
                    )
                except Exception:
                    pass
        return

    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, text, parse_mode="HTML")
            for photo in order.photos[:5]:
                await bot.send_photo(admin_id, photo.file_id)
        except Exception:
            pass


@router.message(Command("admin"))
async def cmd_admin(message: Message) -> None:
    if not is_admin(message.from_user.id):
        return

    async with async_session() as session:
        new_count = await get_orders(session, status=OrderStatus.NEW.value)
        in_progress = await get_orders(session, status=OrderStatus.IN_PROGRESS.value)

    group_info = (
        f"📂 Группа клиентов: {'настроена ✅' if ADMIN_GROUP_ID else 'не настроена ❌'}"
    )

    await message.answer(
        f"👨‍💼 <b>Админ-панель</b>\n\n"
        f"{group_info}\n"
        f"🆕 Новых заявок: {len(new_count)}\n"
        f"⏳ В работе: {len(in_progress)}\n\n"
        f"Все диалоги клиентов — в группе с топиками.\n"
        f"Ответьте клиенту прямо в его топике.\n\n"
        f"/orders — новые заявки\n"
        f"/order ID — детали\n"
        f"/status ID статус — сменить статус\n"
        f"/setup — проверить группу",
        parse_mode="HTML",
    )


@router.message(Command("setup"))
async def cmd_setup(message: Message, bot: Bot) -> None:
    if not is_admin(message.from_user.id):
        return

    if not ADMIN_GROUP_ID:
        await message.answer(
            "❌ ADMIN_GROUP_ID не задан в .env\n\n"
            "1. Создайте супергруппу\n"
            "2. Включите «Темы» в настройках\n"
            "3. Добавьте бота как админа (управление топиками)\n"
            "4. Узнайте ID группы через @RawDataBot\n"
            "5. Пропишите ADMIN_GROUP_ID в .env"
        )
        return

    try:
        chat = await bot.get_chat(ADMIN_GROUP_ID)
        me = await bot.get_me()
        member = await bot.get_chat_member(ADMIN_GROUP_ID, me.id)
        is_forum = getattr(chat, "is_forum", False)
        is_admin_member = member.status in ("administrator", "creator")

        await message.answer(
            f"✅ Группа: {chat.title}\n"
            f"ID: <code>{ADMIN_GROUP_ID}</code>\n"
            f"Топики: {'✅' if is_forum else '❌ включите в настройках группы'}\n"
            f"Бот админ: {'✅' if is_admin_member else '❌ добавьте бота админом'}",
            parse_mode="HTML",
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка доступа к группе: {e}")


@router.message(Command("orders"))
async def cmd_orders(message: Message) -> None:
    if not is_admin(message.from_user.id):
        return

    async with async_session() as session:
        orders = await get_orders(session, status=OrderStatus.NEW.value, limit=20)

    if not orders:
        await message.answer("Новых заявок нет.")
        return

    for order in orders:
        user = order.user
        username = f"@{user.username}" if user.username else "—"
        text = (
            f"<b>#{order.id}</b> — {STATUS_LABELS.get(order.status, order.status)}\n"
            f"👤 {user.first_name or ''} {user.last_name or ''} ({username})\n"
            f"📅 {order.created_at.strftime('%d.%m.%Y %H:%M')}\n"
        )
        if order.link:
            text += f"🔗 {order.link[:80]}{'...' if len(order.link) > 80 else ''}\n"
        text += f"📷 {len(order.photos)} фото"
        if user.topic_id and ADMIN_GROUP_ID:
            text += f"\n💬 Топик: t.me/c/{str(ADMIN_GROUP_ID)[4:]}/{user.topic_id}"
        await message.answer(text, parse_mode="HTML")


@router.message(Command("order"))
async def cmd_order_detail(message: Message) -> None:
    if not is_admin(message.from_user.id):
        return

    parts = message.text.split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer("Использование: /order 123")
        return

    order_id = int(parts[1])
    async with async_session() as session:
        order = await get_order(session, order_id)

    if not order:
        await message.answer("Заявка не найдена.")
        return

    user = order.user
    text = (
        f"<b>Заявка #{order.id}</b>\n"
        f"Статус: {STATUS_LABELS.get(order.status, order.status)}\n\n"
        f"👤 {user.first_name or ''} {user.last_name or ''}\n"
        f"Username: @{user.username or '—'}\n"
        f"Telegram ID: <code>{user.telegram_id}</code>\n"
        f"📅 {order.created_at.strftime('%d.%m.%Y %H:%M')}\n\n"
    )
    if order.link:
        text += f"🔗 {order.link}\n"
    if order.text:
        text += f"📝 {order.text}\n"
    if order.admin_note:
        text += f"\n💬 Заметка: {order.admin_note}\n"
    text += f"\n📷 Фото: {len(order.photos)} шт."

    await message.answer(text, parse_mode="HTML")
    for photo in order.photos:
        await message.answer_photo(photo.file_id)


@router.message(Command("status"))
async def cmd_status(message: Message, bot: Bot) -> None:
    if not is_admin(message.from_user.id):
        return

    parts = message.text.split(maxsplit=2)
    if len(parts) < 3 or not parts[1].isdigit():
        await message.answer("Использование: /status 123 in_progress")
        return

    order_id = int(parts[1])
    new_status = parts[2].strip().lower()
    valid = {s.value for s in OrderStatus}
    if new_status not in valid:
        await message.answer(f"Статус должен быть: {', '.join(valid)}")
        return

    async with async_session() as session:
        order = await update_order_status(session, order_id, new_status)

    if not order:
        await message.answer("Заявка не найдена.")
        return

    await message.answer(
        f"✅ Заявка #{order_id} → {STATUS_LABELS.get(new_status, new_status)}"
    )

    status_messages = {
        OrderStatus.IN_PROGRESS.value: (
            f"⏳ Ваша заявка #{order_id} принята в работу. "
            "Менеджер скоро свяжется с вами."
        ),
        OrderStatus.COMPLETED.value: (
            f"✅ Ваша заявка #{order_id} выполнена! "
            "Менеджер отправит вам готовый ролик."
        ),
        OrderStatus.CANCELLED.value: (
            f"❌ Заявка #{order_id} отменена. "
            "Если это ошибка — напишите нам."
        ),
    }
    if new_status in status_messages:
        try:
            async with async_session() as session:
                full_order = await get_order(session, order_id)
            if full_order:
                await bot.send_message(
                    full_order.user.telegram_id, status_messages[new_status]
                )
                if full_order.user.topic_id:
                    await notify_topic(
                        bot,
                        full_order.user,
                        f"ℹ️ Статус заявки #{order_id} → "
                        f"{STATUS_LABELS.get(new_status, new_status)}",
                    )
        except Exception:
            pass


@router.message(Command("reply"))
async def cmd_reply(message: Message, bot: Bot) -> None:
    if not is_admin(message.from_user.id):
        return

    parts = message.text.split(maxsplit=2)
    if len(parts) < 3 or not parts[1].isdigit():
        await message.answer("Использование: /reply 123456789 Ваш текст")
        return

    telegram_id = int(parts[1])
    reply_text = parts[2]

    try:
        await bot.send_message(
            telegram_id,
            f"💬 Сообщение от менеджера:\n\n{reply_text}",
        )
        async with async_session() as session:
            user = await get_user_by_telegram_id(session, telegram_id)
        if user:
            await notify_topic(bot, user, f"↩️ Админ ответил:\n{reply_text}")
        await message.answer(f"✅ Отправлено пользователю {telegram_id}")
    except Exception as e:
        await message.answer(f"❌ Не удалось отправить: {e}")
