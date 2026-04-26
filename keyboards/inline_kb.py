from aiogram.utils.keyboard import InlineKeyboardBuilder


def main_menu_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text="📝 Записаться", callback_data="book")
    return builder.as_markup()
