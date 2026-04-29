"""Reply‑клавиатуры, которые показываются над строкой ввода."""

from aiogram.types import ReplyKeyboardMarkup, KeyboardButton


def main_reply_kb() -> ReplyKeyboardMarkup:
    """Главная клавиатура с кнопкой «Записаться», показывается всегда."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text='📝 Записаться')]
        ],
        resize_keyboard=True,
        one_time_keyboard=False
    )
