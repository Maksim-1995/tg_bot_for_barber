"""Обработчики команд и callback'ов для клиентов."""

from datetime import date, datetime, time

from aiogram import Router, types, F, Bot
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove
)

from keyboards.reply_kb import main_reply_kb
from handlers.fsm import BookingForm
from database import async_session_maker
from services.db_service import (
    get_services,
    get_masters_by_service,
    get_or_create_user,
    create_appointment
)
from services.calendar_service import generate_date_keyboard, get_free_slots
from utils.constants import SALON_ADDRESS
from utils.validators import (
    validate_name,
    validate_phone, 
    sanitize_comment
)
from models import Service, Master, User


from aiogram.exceptions import TelegramBadRequest

async def safe_edit_text(message: types.Message, text: str, reply_markup=None):
    """
    Безопасное редактирование сообщения:
    если сообщение не изменилось – игнорирует ошибку Telegram.
    """
    try:
        await message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest as error:
        if 'message is not modified' not in str(error):
            raise  # если ошибка другая – пробрасываем дальше.

# Клавиатура с кнопкой отмены, показывается при текстовых вводах.
CANCEL_KEYBOARD = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text='❌ Отмена')]],
    resize_keyboard=True,
    one_time_keyboard=True
)

user_router = Router()


# -------------------------------------------------------------------
# Вспомогательная функция старта записи (используется из разных мест).
async def start_booking(target: types.Message | types.CallbackQuery, state: FSMContext):
    """Общая логика начала записи: показывает список услуг."""
    async with async_session_maker() as session:
        services = await get_services(session)
    if not services:
        text = 'В данный момент нет доступных услуг.'
        if isinstance(target, types.Message):
            await target.answer(text)
        else:
            await target.message.edit_text(text)
            await target.answer()
        return
    builder = InlineKeyboardBuilder()
    for s in services:
        builder.button(text=f'{s.name} ({s.duration} мин)', callback_data=f'service_{s.id}')
    builder.button(text='◀️ Назад', callback_data='cancel')
    builder.adjust(1)
    text = 'Выберите услугу:'
    if isinstance(target, types.Message):
        await target.answer(text, reply_markup=builder.as_markup())
        await state.set_state(BookingForm.waiting_for_service)
    else:
        await target.message.edit_text(text, reply_markup=builder.as_markup())
        await state.set_state(BookingForm.waiting_for_service)
        await target.answer()


# -------------------------------------------------------------------
# Команда /start – приветствие с постоянной кнопкой «Записаться».
@user_router.message(CommandStart())
async def start_command(message: types.Message):
    """Приветствие и главное меню."""
    await message.answer(
        'Добро пожаловать в парикмахерскую «Народная цирюльня»!',
        reply_markup=main_reply_kb()
    )


# -------------------------------------------------------------------
# Запуск записи по reply-кнопке «📝 Записаться».
@user_router.message(F.text == '📝 Записаться')
async def handle_reply_book(message: types.Message, state: FSMContext):
    """Запуск сценария записи по Reply-кнопке."""
    await start_booking(message, state)


# -------------------------------------------------------------------
# Запуск записи по inline-кнопке (оставлено на случай, если используется).
@user_router.callback_query(F.data == 'book')
async def book_service(callback: types.CallbackQuery, state: FSMContext):
    """Запуск сценария записи по Inline-кнопке."""
    await start_booking(callback, state)


# -------------------------------------------------------------------
# FSM-обработчики процесса записи.

@user_router.callback_query(BookingForm.waiting_for_service, F.data.startswith('service_'))
async def service_chosen(callback: types.CallbackQuery, state: FSMContext):
    """Пользователь выбрал услугу, показать мастеров."""
    service_id = int(callback.data.split('_')[1])
    await state.update_data(service_id=service_id)
    async with async_session_maker() as session:
        masters = await get_masters_by_service(session, service_id)
    if not masters:
        await safe_edit_text(callback.message,
            'К сожалению, нет мастеров, выполняющих эту услугу.'
        )
        await state.clear()
        await callback.answer()
        return
    builder = InlineKeyboardBuilder()
    for m in masters:
        desc = f' — {m.description}' if m.description else ''
        builder.button(text=f'{m.full_name}{desc}', callback_data=f'master_{m.id}')
    builder.button(text='◀️ Назад', callback_data='cancel')
    builder.adjust(1)
    await safe_edit_text(callback.message, 'Выберите мастера:', reply_markup=builder.as_markup())
    await state.set_state(BookingForm.waiting_for_master)
    await callback.answer()


@user_router.callback_query(BookingForm.waiting_for_master, F.data.startswith('master_'))
async def master_chosen(callback: types.CallbackQuery, state: FSMContext):
    """Пользователь выбрал мастера, показать календарь."""
    master_id = int(callback.data.split('_')[1])
    await state.update_data(master_id=master_id)
    date_keyboard = await generate_date_keyboard()
    await safe_edit_text(callback.message,
        'Выберите удобную дату:',
        reply_markup=date_keyboard.as_markup()
    )
    await state.set_state(BookingForm.waiting_for_date)
    await callback.answer()


@user_router.callback_query(BookingForm.waiting_for_date, F.data.startswith('date_'))
async def date_chosen(callback: types.CallbackQuery, state: FSMContext):
    """Пользователь выбрал дату, показать свободные слоты."""
    date_str = callback.data.split('_', 1)[1]
    chosen_date = date.fromisoformat(date_str)
    await state.update_data(chosen_date=chosen_date.isoformat())
    user_data = await state.get_data()
    master_id = user_data['master_id']
    service_id = user_data['service_id']
    async with async_session_maker() as session:
        free_slots = await get_free_slots(session, master_id, service_id, chosen_date)
    if not free_slots:
        await safe_edit_text(callback.message,
            'На эту дату нет свободного времени. Выберите другую дату.',
            reply_markup=(await generate_date_keyboard()).as_markup()
        )
        await callback.answer()
        return
    builder = InlineKeyboardBuilder()
    for slot in free_slots:
        builder.button(text=slot, callback_data=f'slot_{slot}')
    builder.button(text='◀️ Назад', callback_data='cancel')
    builder.adjust(4)
    await safe_edit_text(callback.message,
        'Выберите время:',
        reply_markup=builder.as_markup()
    )
    await state.set_state(BookingForm.waiting_for_time)
    await callback.answer()


@user_router.callback_query(BookingForm.waiting_for_time, F.data.startswith('slot_'))
async def time_chosen(callback: types.CallbackQuery, state: FSMContext):
    """Пользователь выбрал время, запросить имя."""
    slot_str = callback.data.split('_', 1)[1]
    await state.update_data(slot_time=slot_str)
    # Сначала отправляем Reply‑кнопку отмены
    await callback.message.answer(
        'Пожалуйста, введите ваше имя:',
        reply_markup=CANCEL_KEYBOARD
    )
    await state.set_state(BookingForm.waiting_for_name)
    await callback.answer()


@user_router.message(BookingForm.waiting_for_name)
async def process_name(message: types.Message, state: FSMContext):
    """Пользователь ввёл имя, запросить телефон."""
    if message.text == '❌ Отмена':
        await cancel_booking(message, state)
        return
    name = message.text.strip()
    is_valid, error_message = validate_name(name)
    if not is_valid:
        await message.reply(error_message)
        return
    await state.update_data(client_name=name)
    contact_keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text='📱 Отправить номер', request_contact=True)],
            [KeyboardButton(text='❌ Отмена')]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    await message.answer(
        'Укажите ваш номер телефона или нажмите кнопку «Отправить номер».',
        reply_markup=contact_keyboard
    )
    await state.set_state(BookingForm.waiting_for_phone)


@user_router.message(BookingForm.waiting_for_phone, F.contact | F.text)
async def process_phone(message: types.Message, state: FSMContext):
    """Пользователь ввёл телефон или отправил контакт, запросить комментарий."""
    if message.text == '❌ Отмена':
        await cancel_booking(message, state)
        return
    if message.contact:
        phone = message.contact.phone_number
        is_valid = True
        error_message = None
    else:
        phone = message.text.strip()
        is_valid, error_message = validate_phone(phone)

    if not is_valid:
        await message.reply(error_message)
        return

    await state.update_data(client_phone=phone)
    await message.answer(
        'Оставьте комментарий к записи (необязательно) или нажмите «Пропустить».',
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text='Пропустить ➡️')],
                [KeyboardButton(text='❌ Отмена')]
            ],
            resize_keyboard=True,
            one_time_keyboard=True
        )
    )
    await state.set_state(BookingForm.waiting_for_comment)


@user_router.message(BookingForm.waiting_for_comment, F.text)
async def process_comment(message: types.Message, state: FSMContext):
    """Обработка комментария и вывод подтверждения."""
    if message.text == '❌ Отмена':
        await cancel_booking(message, state)
        return
    if message.text == 'Пропустить ➡️':
        comment = None
    else:
        comment, error_message = sanitize_comment(message.text)
        if error_message:
            await message.reply(error_message)
            return
    await state.update_data(comment=comment)
    user_data = await state.get_data()
    chosen_date = date.fromisoformat(user_data['chosen_date'])
    async with async_session_maker() as session:
        service = await session.get(Service, user_data['service_id'])
        master = await session.get(Master, user_data['master_id'])
    summary = (
        f'Проверьте детали записи:\n'
        f'Услуга: {service.name}\n'
        f'Мастер: {master.full_name}\n'
        f'Дата: {chosen_date.strftime("%d.%m.%Y")}\n'
        f'Время: {user_data["slot_time"]}\n'
        f'Имя: {user_data["client_name"]}\n'
        f'Телефон: {user_data["client_phone"]}'
    )
    if comment:
        summary += f'\nКомментарий: {comment}'
    builder = InlineKeyboardBuilder()
    builder.button(text='✅ Подтвердить', callback_data='confirm_booking')
    builder.button(text='❌ Отменить', callback_data='cancel')
    await message.answer(summary, reply_markup=builder.as_markup())
    await state.set_state(BookingForm.waiting_for_confirmation)


@user_router.callback_query(
    BookingForm.waiting_for_confirmation,
    F.data == 'confirm_booking'
)
async def confirm_booking(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    """Подтверждение записи: сохранение в БД, уведомление администраторам."""
    user_data = await state.get_data()
    async with async_session_maker() as session:
        user = await get_or_create_user(
            session,
            telegram_id=callback.from_user.id,
            full_name=user_data['client_name'],
            phone=user_data['client_phone']
        )
        chosen_date = date.fromisoformat(user_data['chosen_date'])
        hour, minute = map(int, user_data['slot_time'].split(':'))
        date_time = datetime.combine(chosen_date, time(hour, minute))

        try:
            appointment = await create_appointment(
                session,
                user.id,
                user_data['master_id'],
                user_data['service_id'],
                date_time,
                comment=user_data.get('comment')
            )
        except ValueError as error:
            await safe_edit_text(callback.message,f'Ошибка: {error}')
            await state.clear()
            await callback.answer()
            return

        # Явная загрузка связанных объектов (чтобы избежать DetachedInstanceError)
        service_obj = await session.get(Service, user_data['service_id'])
        master_obj = await session.get(Master, user_data['master_id'])

        client_name = user_data['client_name']
        service_name = service_obj.name
        master_name = master_obj.full_name
        date_time_str = appointment.date_time.strftime('%d.%m.%Y в %H:%M')
        phone = user_data['client_phone']
        comment = appointment.comment

    # Отправляем уведомления администраторам
    from services.notifications import notify_admins
    await notify_admins(bot, client_name, service_name, master_name, date_time_str, phone, comment)

    await safe_edit_text(callback.message,
        f'✅ Вы записаны! Ждём вас по адресу: {SALON_ADDRESS}'
    )
    await state.clear()
    await callback.answer()


# -------------------------------------------------------------------
# Универсальные обработчики (кнопка отмены и приветствие)

@user_router.callback_query(F.data == 'cancel')
async def cancel_callback(callback: types.CallbackQuery, state: FSMContext):
    """Отмена через inline-кнопку (назад/отмена)."""
    await state.clear()
    await start_command(callback.message)
    await callback.answer()


async def cancel_booking(message: types.Message, state: FSMContext):
    """Отмена через текстовую кнопку «❌ Отмена»."""
    await state.clear()
    await message.answer('Запись отменена.', reply_markup=types.ReplyKeyboardRemove())
    await start_command(message)


@user_router.message(F.text == '❌ Отмена')
async def handle_cancel_text(message: types.Message, state: FSMContext):
    """Обработчик нажатия «❌ Отмена» вне состояний."""
    await cancel_booking(message, state)


@user_router.message(~F.text.startswith('/'))
async def greeting_on_any_message(message: types.Message, state: FSMContext):
    """При любом другом сообщении (не команда) показываем приветствие, если не в процессе записи."""
    current_state = await state.get_state()
    if current_state is None:
        await message.answer(
            'Добро пожаловать в парикмахерскую «Народная цирюльня»!',
            reply_markup=main_reply_kb()
        )
