from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)


def main_menu_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📋 Новая заявка")],
            [KeyboardButton(text="📞 Мои заявки")],
        ],
        resize_keyboard=True,
    )


def order_actions_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Отправить заявку", callback_data="order:submit")],
            [InlineKeyboardButton(text="➕ Добавить фото", callback_data="order:add_photo")],
            [InlineKeyboardButton(text="🔗 Добавить ссылку", callback_data="order:add_link")],
            [InlineKeyboardButton(text="📝 Добавить текст", callback_data="order:add_text")],
            [InlineKeyboardButton(text="❌ Отменить", callback_data="order:cancel")],
        ]
    )


def content_inline_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Готово", callback_data="content:done"),
                InlineKeyboardButton(text="❌ Отмена", callback_data="content:cancel"),
            ]
        ]
    )
