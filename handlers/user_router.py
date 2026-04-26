from aiogram import Router, types, F
from aiogram.filters import CommandStart

from aiogram.fsm.context import FSMContext
from keyboards.inline_kb import main_menu_kb
from handlers.fsm import BookingForm


user_router = Router()

@user_router.message(CommandStart())
async def start_command(message: types.Message):
    await message.answer(
        "Добро пожаловать в парикмахерскую «Народная»!",
        reply_markup=main_menu_kb()
    )

@user_router.callback_query(F.data == "book")
async def book_service(callback: types.CallbackQuery, state: FSMContext):
    # Здесь запускаем сценарий выбора услуги
    await callback.message.edit_text("Выберите услугу:")
    await state.set_state(BookingForm.waiting_for_service)
    await callback.answer()
