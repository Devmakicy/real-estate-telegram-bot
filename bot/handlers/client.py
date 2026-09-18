import re

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove

from bot.keyboards import content_inline_kb, main_menu_kb, order_actions_kb
from bot.states import OrderForm
from config import WELCOME_TEXT
from database.crud import create_order, get_or_create_user, get_orders
from database.models import OrderStatus
from database.session import async_session

router = Router()

URL_PATTERN = re.compile(r"https?://\S+")


def format_order_summary(data: dict) -> str:
    link = data.get("link")
    text = data.get("text")
    photos = data.get("photos", [])

    lines = ["📋 <b>Ваша заявка:</b>\n"]
    if link:
        lines.append(f"🔗 Ссылка: {link}")
    else:
        lines.append("🔗 Ссылка: не указана")

    lines.append(f"📷 Фото: {len(photos)} шт.")

    if text:
        lines.append(f"\n📝 Комментарий:\n{text}")
    else:
        lines.append("\n📝 Комментарий: не указан")

    lines.append("\nПроверьте данные и нажмите «Отправить заявку».")
    return "\n".join(lines)


async def init_order_state(state: FSMContext) -> None:
    await state.clear()
    await state.set_state(OrderForm.waiting_content)
    await state.update_data(link=None, text=None, photos=[])


async def save_photo(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    photos = data.get("photos", [])
    photo = message.photo[-1]
    photos.append(photo.file_id)
    await state.update_data(photos=photos)
    await message.answer(
        f"📷 Фото добавлено ({len(photos)} шт.). "
        "Можете отправить ещё или нажмите «✅ Готово».",
        reply_markup=content_inline_kb(),
    )


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, bot: Bot) -> None:
    from bot.services.topics import get_or_create_topic

    await get_or_create_topic(bot, message.from_user)
    await init_order_state(state)
    await message.answer(WELCOME_TEXT, reply_markup=ReplyKeyboardRemove())


@router.message(F.text == "📋 Новая заявка")
async def new_order(message: Message, state: FSMContext) -> None:
    await init_order_state(state)
    await message.answer(WELCOME_TEXT, reply_markup=ReplyKeyboardRemove())


@router.message(F.text == "📞 Мои заявки")
async def my_orders(message: Message) -> None:
    async with async_session() as session:
        user = await get_or_create_user(
            session,
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            last_name=message.from_user.last_name,
        )
        orders = await get_orders(session)
        user_orders = [o for o in orders if o.user_id == user.id]

    if not user_orders:
        await message.answer("У вас пока нет заявок. Нажмите «📋 Новая заявка».")
        return

    status_labels = {
        OrderStatus.NEW.value: "🆕 Новая",
        OrderStatus.IN_PROGRESS.value: "⏳ В работе",
        OrderStatus.COMPLETED.value: "✅ Готово",
        OrderStatus.CANCELLED.value: "❌ Отменена",
    }

    for order in user_orders[:10]:
        status = status_labels.get(order.status, order.status)
        text = (
            f"<b>Заявка #{order.id}</b> — {status}\n"
            f"📅 {order.created_at.strftime('%d.%m.%Y %H:%M')}\n"
        )
        if order.link:
            text += f"🔗 {order.link}\n"
        if order.text:
            text += f"📝 {order.text[:100]}{'...' if len(order.text or '') > 100 else ''}\n"
        text += f"📷 Фото: {len(order.photos)} шт."
        await message.answer(text, parse_mode="HTML")


@router.message(F.text == "❌ Отмена")
async def cancel_flow(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Заявка отменена.", reply_markup=main_menu_kb())


async def finish_content_collection(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    if not data.get("link") and not data.get("photos"):
        await message.answer(
            "Нужна хотя бы ссылка или одно фото. Отправьте данные и нажмите «Готово».",
            reply_markup=content_inline_kb(),
        )
        return

    await state.set_state(OrderForm.confirm)
    await message.answer(
        format_order_summary(data),
        reply_markup=order_actions_kb(),
        parse_mode="HTML",
    )


@router.message(OrderForm.waiting_content, F.text == "✅ Готово")
async def content_done_text(message: Message, state: FSMContext) -> None:
    await finish_content_collection(message, state)


@router.callback_query(F.data == "content:done")
async def content_done_cb(callback: CallbackQuery, state: FSMContext) -> None:
    await finish_content_collection(callback.message, state)
    await callback.answer()


@router.callback_query(F.data == "content:cancel")
async def content_cancel_cb(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.answer("Заявка отменена.", reply_markup=main_menu_kb())
    await callback.answer()


@router.message(F.photo)
async def receive_photo(message: Message, state: FSMContext) -> None:
    current = await state.get_state()
    if current != OrderForm.waiting_content.state:
        await init_order_state(state)
    await save_photo(message, state)


@router.message(F.document)
async def receive_document(message: Message, state: FSMContext) -> None:
    if not message.document or not message.document.mime_type:
        return
    if not message.document.mime_type.startswith("image/"):
        await message.answer(
            "Пожалуйста, отправьте фото как изображение, не как другой файл."
        )
        return

    current = await state.get_state()
    if current != OrderForm.waiting_content.state:
        await init_order_state(state)

    data = await state.get_data()
    photos = data.get("photos", [])
    photos.append(message.document.file_id)
    await state.update_data(photos=photos)
    await message.answer(
        f"📷 Фото добавлено ({len(photos)} шт.). "
        "Можете отправить ещё или нажмите «✅ Готово».",
        reply_markup=content_inline_kb(),
    )


@router.message(OrderForm.waiting_content, F.text)
async def receive_link_or_text(message: Message, state: FSMContext) -> None:
    text = message.text.strip()
    if text in ("❌ Отмена", "✅ Готово"):
        return

    if URL_PATTERN.match(text):
        await state.update_data(link=text)
        await message.answer(
            f"🔗 Ссылка сохранена.\nОтправьте фото или нажмите «✅ Готово».",
            reply_markup=content_inline_kb(),
        )
    else:
        await state.update_data(text=text)
        await message.answer(
            "📝 Текст сохранён. Отправьте ссылку/фото или нажмите «✅ Готово».",
            reply_markup=content_inline_kb(),
        )


@router.callback_query(F.data == "order:add_photo")
async def cb_add_photo(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(OrderForm.waiting_content)
    await callback.message.answer(
        "Отправьте фото объекта через 📎",
        reply_markup=ReplyKeyboardRemove(),
    )
    await callback.message.answer("Кнопки:", reply_markup=content_inline_kb())
    await callback.answer()


@router.callback_query(F.data == "order:add_link")
async def cb_add_link(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(OrderForm.waiting_content)
    await callback.message.answer(
        "Отправьте ссылку на объявление.",
        reply_markup=content_inline_kb(),
    )
    await callback.answer()


@router.callback_query(F.data == "order:add_text")
async def cb_add_text(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(OrderForm.waiting_text)
    await callback.message.answer(
        "Напишите комментарий к заявке.",
        reply_markup=content_inline_kb(),
    )
    await callback.answer()


@router.message(OrderForm.waiting_text, F.text)
async def receive_comment(message: Message, state: FSMContext) -> None:
    if message.text == "❌ Отмена":
        return
    await state.update_data(text=message.text.strip())
    data = await state.get_data()
    await state.set_state(OrderForm.confirm)
    await message.answer(
        format_order_summary(data),
        reply_markup=order_actions_kb(),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "order:cancel")
async def cb_cancel_order(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.answer("Заявка отменена.", reply_markup=main_menu_kb())
    await callback.answer()


@router.callback_query(F.data == "order:submit")
async def cb_submit_order(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    from bot.handlers.admin import notify_admins_new_order

    data = await state.get_data()
    if not data.get("link") and not data.get("photos"):
        await callback.answer("Нужна ссылка или фото!", show_alert=True)
        return

    async with async_session() as session:
        user = await get_or_create_user(
            session,
            telegram_id=callback.from_user.id,
            username=callback.from_user.username,
            first_name=callback.from_user.first_name,
            last_name=callback.from_user.last_name,
        )
        order = await create_order(
            session,
            user_id=user.id,
            link=data.get("link"),
            text=data.get("text"),
            photo_file_ids=data.get("photos", []),
        )

    await state.clear()
    await callback.message.answer(
        f"✅ Заявка <b>#{order.id}</b> принята!\n\n"
        "Менеджер свяжется с вами в ближайшее время.\n"
        "Стоимость готового видео: <b>15 000 ₽</b>.",
        reply_markup=main_menu_kb(),
        parse_mode="HTML",
    )
    await callback.answer("Заявка отправлена!")

    from bot.services.topics import get_or_create_topic

    await get_or_create_topic(bot, callback.from_user)
    await notify_admins_new_order(bot, order.id)


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(WELCOME_TEXT)


@router.message(F.chat.type == "private", F.text)
async def private_text_fallback(message: Message) -> None:
    """Ловит любой текст в личке (ответ клиента админу и т.д.)."""
    if message.text.startswith("/"):
        return
    if message.text in ("📋 Новая заявка", "📞 Мои заявки", "✅ Готово", "❌ Отмена"):
        return
