"""Обработчики команд и callback'ов для клиентов."""

from datetime import date, datetime, time

from aiogram import Router, types, F, Bot
from aiogram.filters import CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
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
from services.notifications import format_client_booking_confirmed_message, notify_admins
from utils.validators import (
    normalize_phone,
    validate_name,
    validate_phone, 
    sanitize_comment
)
from utils.interaction_guard import callback_action_lock, is_expected_state
from models import Service, Master


from aiogram.exceptions import TelegramBadRequest

async def safe_edit_text(message: types.Message, text: str, reply_markup=None):
    """
    Безопасное редактирование сообщения.
    
    Если сообщение не изменилось – игнорирует ошибку Telegram.
    """
    if not message:
        return
    try:
        await message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest as error:
        error_text = str(error)
        if 'message is not modified' in error_text:
            return
        if "message can't be edited" in error_text or 'message to edit not found' in error_text:
            await message.answer(text, reply_markup=reply_markup)
            return
        raise  # если ошибка другая – пробрасываем дальше.

# Клавиатура с кнопкой отмены, показывается при текстовых вводах.
CANCEL_KEYBOARD = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text='❌ Отмена')]],
    resize_keyboard=True,
    one_time_keyboard=True
)

user_router = Router()


async def answer_stale_booking_callback(callback: types.CallbackQuery):
    await callback.answer('Это действие уже обработано. Начните запись заново.', show_alert=True)


def booking_restart_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text='📝 Записаться заново', callback_data='book')
    builder.adjust(1)
    return builder.as_markup()


async def finish_booking_message(message: types.Message, state: FSMContext, text: str):
    await state.clear()
    await message.answer(text, reply_markup=types.ReplyKeyboardRemove())
    await start_command(message)


async def finish_booking_callback(callback: types.CallbackQuery, state: FSMContext, text: str):
    await state.clear()
    await safe_edit_text(callback.message, text, reply_markup=booking_restart_kb())
    await callback.answer()


async def answer_unmatched_booking_callback(callback: types.CallbackQuery, state: FSMContext):
    current_state = await state.get_state()
    if current_state:
        await callback.answer(
            'Эта кнопка не относится к текущему шагу. Завершите запись или нажмите «Отмена».',
            show_alert=True,
        )
        return
    await callback.answer('Кнопка устарела. Начните запись заново.', show_alert=True)
    await safe_edit_text(
        callback.message,
        'Эта кнопка уже неактуальна. Можно начать запись заново.',
        reply_markup=booking_restart_kb(),
    )


def parse_prefixed_int(data: str | None, prefix: str) -> int | None:
    if not data or not data.startswith(prefix):
        return None
    raw_value = data.removeprefix(prefix)
    if not raw_value.isdigit():
        return None
    return int(raw_value)


def parse_prefixed_date(data: str | None, prefix: str) -> date | None:
    if not data or not data.startswith(prefix):
        return None
    try:
        return date.fromisoformat(data.removeprefix(prefix))
    except ValueError:
        return None


def normalize_slot_value(raw_value: str | None) -> str | None:
    if not raw_value:
        return None
    try:
        slot_time = time.fromisoformat(raw_value)
    except ValueError:
        return None
    if slot_time.second or slot_time.microsecond or slot_time.tzinfo is not None:
        return None
    return slot_time.isoformat(timespec='minutes')


def parse_slot_value(data: str | None, prefix: str) -> str | None:
    if not data or not data.startswith(prefix):
        return None
    return normalize_slot_value(data.removeprefix(prefix))


# Вспомогательная функция старта записи.
async def start_booking(target: types.Message | types.CallbackQuery, state: FSMContext):
    """Общая логика начала записи: показывает список услуг."""
    await state.clear()
    async with async_session_maker() as session:
        services = await get_services(session)
    if not services:
        text = 'В данный момент нет доступных услуг.'
        if isinstance(target, types.Message):
            await target.answer(text, reply_markup=main_reply_kb())
        else:
            await safe_edit_text(target.message, text)
            await target.answer()
        return
    builder = InlineKeyboardBuilder()
    for s in services:
        builder.button(text=f'{s.name} ({s.duration} мин)', callback_data=f'service_{s.id}')
    builder.button(text='🏠 В главное меню', callback_data='cancel')
    builder.adjust(1)
    text = 'Выберите услугу:'
    if isinstance(target, types.Message):
        await target.answer(text, reply_markup=builder.as_markup())
        await state.set_state(BookingForm.waiting_for_service)
    else:
        await safe_edit_text(target.message, text, reply_markup=builder.as_markup())
        await state.set_state(BookingForm.waiting_for_service)
        await target.answer()


# Команда /start – приветствие с постоянной кнопкой «Записаться».
@user_router.message(CommandStart())
async def start_command(message: types.Message):
    """Приветствие и главное меню."""
    await message.answer(
        'Добро пожаловать в парикмахерскую «Народная цирюльня»!',
        reply_markup=main_reply_kb()
    )


# Запуск записи по reply-кнопке «📝 Записаться».
@user_router.message(F.text == '📝 Записаться')
async def handle_reply_book(message: types.Message, state: FSMContext):
    """Запуск сценария записи по Reply-кнопке."""
    await start_booking(message, state)


# Запуск записи по inline-кнопке.
@user_router.callback_query(F.data == 'book')
async def book_service(callback: types.CallbackQuery, state: FSMContext):
    """Запуск сценария записи по Inline-кнопке."""
    await start_booking(callback, state)


# FSM-обработчики процесса записи.
@user_router.callback_query(BookingForm.waiting_for_service, F.data.startswith('service_'))
async def service_chosen(callback: types.CallbackQuery, state: FSMContext):
    """Пользователь выбрал услугу, показать мастеров."""
    async with callback_action_lock(callback, 'user_choose_service'):
        if not await is_expected_state(state, BookingForm.waiting_for_service):
            await answer_stale_booking_callback(callback)
            return
        service_id = parse_prefixed_int(callback.data, 'service_')
        if service_id is None:
            await callback.answer('Кнопка устарела. Начните запись заново.', show_alert=True)
            return
        await state.update_data(service_id=service_id)
        async with async_session_maker() as session:
            masters = await get_masters_by_service(session, service_id)
        if not masters:
            await finish_booking_callback(
                callback,
                state,
                'К сожалению, сейчас нет мастеров, выполняющих эту услугу.',
            )
            return
        builder = InlineKeyboardBuilder()
        for m in masters:
            desc = f' — {m.description}' if m.description else ''
            builder.button(text=f'{m.full_name}{desc}', callback_data=f'master_{m.id}')
        builder.button(text='🏠 В главное меню', callback_data='cancel')
        builder.adjust(1)
        await safe_edit_text(
            callback.message,
            'Выберите мастера:',
            reply_markup=builder.as_markup(),
        )
        await state.set_state(BookingForm.waiting_for_master)
        await callback.answer()


@user_router.callback_query(BookingForm.waiting_for_master, F.data.startswith('master_'))
async def master_chosen(callback: types.CallbackQuery, state: FSMContext):
    """Пользователь выбрал мастера, показать календарь."""
    async with callback_action_lock(callback, 'user_choose_master'):
        if not await is_expected_state(state, BookingForm.waiting_for_master):
            await answer_stale_booking_callback(callback)
            return
        master_id = parse_prefixed_int(callback.data, 'master_')
        if master_id is None:
            await callback.answer('Кнопка устарела. Начните запись заново.', show_alert=True)
            return
        await state.update_data(master_id=master_id)
        date_keyboard = await generate_date_keyboard()
        await safe_edit_text(
            callback.message,
            'Выберите удобную дату:',
            reply_markup=date_keyboard.as_markup(),
        )
        await state.set_state(BookingForm.waiting_for_date)
        await callback.answer()


@user_router.callback_query(BookingForm.waiting_for_date, F.data.startswith('date_'))
async def date_chosen(callback: types.CallbackQuery, state: FSMContext):
    """Пользователь выбрал дату, показать свободные слоты."""
    async with callback_action_lock(callback, 'user_choose_date'):
        if not await is_expected_state(state, BookingForm.waiting_for_date):
            await answer_stale_booking_callback(callback)
            return
        chosen_date = parse_prefixed_date(callback.data, 'date_')
        if chosen_date is None:
            await callback.answer('Кнопка устарела. Начните запись заново.', show_alert=True)
            return
        await state.update_data(chosen_date=chosen_date.isoformat())
        user_data = await state.get_data()
        try:
            master_id = user_data['master_id']
            service_id = user_data['service_id']
        except KeyError:
            await finish_booking_callback(
                callback,
                state,
                'Данные записи устарели. Начните запись заново.',
            )
            return
        try:
            async with async_session_maker() as session:
                free_slots = await get_free_slots(session, master_id, service_id, chosen_date)
        except ValueError as error:
            await finish_booking_callback(callback, state, f'Ошибка: {error}')
            return
        if not free_slots:
            await safe_edit_text(
                callback.message,
                'На эту дату нет свободного времени. Выберите другую дату.',
                reply_markup=(await generate_date_keyboard()).as_markup(),
            )
            await callback.answer()
            return
        builder = InlineKeyboardBuilder()
        for slot in free_slots:
            builder.button(text=slot, callback_data=f'slot_{slot}')
        builder.button(text='🏠 В главное меню', callback_data='cancel')
        builder.adjust(4)
        await safe_edit_text(
            callback.message,
            'Выберите время:',
            reply_markup=builder.as_markup(),
        )
        await state.set_state(BookingForm.waiting_for_time)
        await callback.answer()


@user_router.callback_query(BookingForm.waiting_for_time, F.data.startswith('slot_'))
async def time_chosen(callback: types.CallbackQuery, state: FSMContext):
    """Пользователь выбрал время, запросить имя."""
    async with callback_action_lock(callback, 'user_choose_time'):
        if not await is_expected_state(state, BookingForm.waiting_for_time):
            await answer_stale_booking_callback(callback)
            return
        slot_str = parse_slot_value(callback.data, 'slot_')
        if slot_str is None:
            await callback.answer('Кнопка устарела. Начните запись заново.', show_alert=True)
            return
        await state.update_data(slot_time=slot_str)
        await callback.message.answer(
            'Пожалуйста, введите ваше имя:',
            reply_markup=CANCEL_KEYBOARD,
        )
        await state.set_state(BookingForm.waiting_for_name)
        await callback.answer()


@user_router.message(BookingForm.waiting_for_name)
async def process_name(message: types.Message, state: FSMContext):
    """Пользователь ввёл имя, запросить телефон."""
    if message.text == '❌ Отмена':
        await cancel_booking(message, state)
        return
    if not message.text:
        await message.reply('Пожалуйста, введите имя текстом.')
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
        if message.contact.user_id and message.contact.user_id != message.from_user.id:
            await message.reply('Пожалуйста, отправьте свой номер телефона.')
            return
        phone = message.contact.phone_number
        is_valid, error_message = validate_phone(phone)
    else:
        phone = message.text.strip()
        is_valid, error_message = validate_phone(phone)

    if not is_valid:
        await message.reply(error_message)
        return

    phone = normalize_phone(phone)
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
    try:
        chosen_date = date.fromisoformat(user_data['chosen_date'])
        service_id = user_data['service_id']
        master_id = user_data['master_id']
        slot_time = user_data['slot_time']
        client_name = user_data['client_name']
        client_phone = user_data['client_phone']
    except (KeyError, ValueError):
        await finish_booking_message(message, state, 'Данные записи устарели. Начните запись заново.')
        return
    async with async_session_maker() as session:
        service = await session.get(Service, service_id)
        master = await session.get(Master, master_id)
    if not service or not master:
        await finish_booking_message(message, state, 'Услуга или мастер больше недоступны. Начните запись заново.')
        return
    summary = (
        f'Проверьте детали записи:\n'
        f'Услуга: {service.name}\n'
        f'Мастер: {master.full_name}\n'
        f'Дата: {chosen_date.strftime("%d.%m.%Y")}\n'
        f'Время: {slot_time}\n'
        f'Имя: {client_name}\n'
        f'Телефон: {client_phone}'
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
    async with callback_action_lock(callback, 'user_confirm_booking'):
        if not await is_expected_state(state, BookingForm.waiting_for_confirmation):
            await answer_stale_booking_callback(callback)
            return

        user_data = await state.get_data()
        try:
            client_name = user_data['client_name']
            client_phone = user_data['client_phone']
            master_id = user_data['master_id']
            service_id = user_data['service_id']
            chosen_date = date.fromisoformat(user_data['chosen_date'])
            slot_value = normalize_slot_value(user_data.get('slot_time'))
            if slot_value is None:
                raise ValueError
            date_time = datetime.combine(chosen_date, time.fromisoformat(slot_value))
        except (KeyError, ValueError):
            await safe_edit_text(
                callback.message,
                'Данные записи устарели. Начните запись заново.',
                reply_markup=booking_restart_kb(),
            )
            await state.clear()
            await callback.answer()
            return

        await safe_edit_text(callback.message, 'Создаю запись...')
        async with async_session_maker() as session:
            user = await get_or_create_user(
                session,
                telegram_id=callback.from_user.id,
                full_name=client_name,
                phone=client_phone,
            )
            try:
                appointment = await create_appointment(
                    session,
                    user.id,
                    master_id,
                    service_id,
                    date_time,
                    client_name=client_name,
                    client_phone=client_phone,
                    comment=user_data.get('comment'),
                )
            except ValueError as error:
                await safe_edit_text(
                    callback.message,
                    f'Ошибка: {error}',
                    reply_markup=booking_restart_kb(),
                )
                await state.clear()
                await callback.answer()
                return

            # Явная загрузка связанных объектов, чтобы избежать DetachedInstanceError.
            service_obj = await session.get(Service, service_id)
            master_obj = await session.get(Master, master_id)
            if not service_obj or not master_obj:
                await safe_edit_text(
                    callback.message,
                    'Услуга или мастер больше недоступны. Начните запись заново.',
                    reply_markup=booking_restart_kb(),
                )
                await state.clear()
                await callback.answer()
                return

            service_name = service_obj.name
            master_name = master_obj.full_name
            date_time_str = appointment.date_time.strftime('%d.%m.%Y в %H:%M')
            comment = appointment.comment

        await notify_admins(
            bot,
            client_name,
            service_name,
            master_name,
            date_time_str,
            client_phone,
            comment,
        )

        await safe_edit_text(
            callback.message,
            format_client_booking_confirmed_message(),
        )
        await state.clear()
        await callback.answer()


# Универсальные обработчики (кнопка отмены и приветствие)
@user_router.callback_query(F.data == 'cancel')
async def cancel_callback(callback: types.CallbackQuery, state: FSMContext):
    """Отмена через inline-кнопку с возвратом в главное меню."""
    await state.clear()
    await start_command(callback.message)
    await callback.answer()


@user_router.callback_query(F.data.startswith('service_'))
async def stale_service_callback(callback: types.CallbackQuery, state: FSMContext):
    await answer_unmatched_booking_callback(callback, state)


@user_router.callback_query(F.data.startswith('master_'))
async def stale_master_callback(callback: types.CallbackQuery, state: FSMContext):
    await answer_unmatched_booking_callback(callback, state)


@user_router.callback_query(F.data.startswith('date_'))
async def stale_date_callback(callback: types.CallbackQuery, state: FSMContext):
    await answer_unmatched_booking_callback(callback, state)


@user_router.callback_query(F.data.startswith('slot_'))
async def stale_slot_callback(callback: types.CallbackQuery, state: FSMContext):
    await answer_unmatched_booking_callback(callback, state)


@user_router.callback_query(F.data == 'confirm_booking')
async def stale_confirm_booking_callback(callback: types.CallbackQuery, state: FSMContext):
    await answer_unmatched_booking_callback(callback, state)


async def cancel_booking(message: types.Message, state: FSMContext):
    """Отмена через текстовую кнопку «❌ Отмена»."""
    await state.clear()
    await message.answer('Запись отменена.', reply_markup=types.ReplyKeyboardRemove())
    await start_command(message)


@user_router.message(F.text == '❌ Отмена')
async def handle_cancel_text(message: types.Message, state: FSMContext):
    """Обработчик нажатия «❌ Отмена» вне состояний."""
    await cancel_booking(message, state)


@user_router.message(StateFilter(None), ~F.text.startswith('/'))
async def greeting_on_any_message(message: types.Message, state: FSMContext):
    """При любом другом сообщении (не команда) показываем приветствие, если не в процессе записи."""
    current_state = await state.get_state()
    if current_state is None:
        await message.answer(
            'Добро пожаловать в парикмахерскую «Народная цирюльня»!',
            reply_markup=main_reply_kb()
        )
