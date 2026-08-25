import shlex
from datetime import date, datetime, time, timedelta

from aiogram import Bot, F, Router, types
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove
from aiogram.utils.keyboard import InlineKeyboardBuilder

from database import async_session_maker
from filters.admin_filter import IsAdmin
from handlers.fsm import (
    AdminBookingManageForm,
    AdminClosedDateForm,
    AdminCreateBookingForm,
    AdminEditMasterForm,
    AdminEditServiceForm,
    AdminMasterForm,
    AdminSalonSettingsForm,
    AdminScheduleForm,
    AdminServiceForm,
)
from services.db_service import (
    add_closed_date,
    add_master,
    add_service,
    cancel_appointment,
    create_appointment,
    get_closed_dates,
    get_future_appointments,
    get_appointment_by_id,
    get_master,
    get_masters,
    get_masters_by_service,
    get_or_create_manual_user,
    get_salon_settings,
    get_service,
    get_services,
    reschedule_appointment,
    remove_closed_date,
    seed_demo_salon,
    set_master_active,
    set_master_services,
    set_service_active,
    set_master_day_off,
    set_master_schedule,
    update_salon_address,
    update_master,
    update_service,
    update_slot_interval,
    validate_slot_interval,
)
from services.calendar_service import get_free_slots
from services.notifications import notify_client_booking_cancelled, notify_client_booking_rescheduled
from utils.constants import DAYS_AHEAD
from utils.interaction_guard import callback_action_lock, is_expected_state
from utils.validators import normalize_phone, sanitize_comment, validate_name, validate_phone


admin_router = Router()
admin_router.message.filter(IsAdmin())
admin_router.callback_query.filter(IsAdmin())

ADMIN_CANCEL_TEXT = '🚫 Отменить настройку'
ADMIN_SKIP_TEXT = 'Пропустить'
INVALID_ADMIN_CALLBACK_TEXT = 'Кнопка устарела или повреждена. Откройте раздел заново.'
DAYS = [
    (0, 'ПН'),
    (1, 'ВТ'),
    (2, 'СР'),
    (3, 'ЧТ'),
    (4, 'ПТ'),
    (5, 'СБ'),
    (6, 'ВС'),
]


def admin_main_menu_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text='Услуги', callback_data='admin_menu_services')
    builder.button(text='Мастера', callback_data='admin_menu_masters')
    builder.button(text='Расписание', callback_data='admin_menu_schedule')
    builder.button(text='Записи', callback_data='admin_menu_bookings')
    builder.button(text='Выходные даты', callback_data='admin_menu_closed_dates')
    builder.button(text='Настройки салона', callback_data='admin_menu_settings')
    builder.adjust(2, 2, 2)
    return builder.as_markup()


def admin_services_menu_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text='Добавить услугу', callback_data='admin_action_add_service')
    builder.button(text='Редактировать услугу', callback_data='admin_action_edit_service')
    builder.button(text='Список услуг', callback_data='admin_action_list_services')
    builder.button(text='Назад', callback_data='admin_menu_main')
    builder.adjust(1)
    return builder.as_markup()


def admin_masters_menu_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text='Добавить мастера', callback_data='admin_action_add_master')
    builder.button(text='Редактировать мастера', callback_data='admin_action_edit_master')
    builder.button(text='Список мастеров', callback_data='admin_action_list_masters')
    builder.button(text='Назад', callback_data='admin_menu_main')
    builder.adjust(1)
    return builder.as_markup()


def admin_schedule_menu_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text='Настроить расписание', callback_data='admin_action_set_schedule')
    builder.button(text='Регулярный выходной', callback_data='admin_action_set_day_off')
    builder.button(text='Назад', callback_data='admin_menu_main')
    builder.adjust(1)
    return builder.as_markup()


def admin_bookings_menu_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text='Создать запись', callback_data='admin_action_create_booking')
    builder.button(text='Управлять записями', callback_data='admin_action_manage_bookings')
    builder.button(text='Посмотреть записи', callback_data='admin_action_view_bookings')
    builder.button(text='Назад', callback_data='admin_menu_main')
    builder.adjust(1)
    return builder.as_markup()


def admin_closed_dates_menu_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text='Добавить выходную дату', callback_data='admin_action_add_closed_date')
    builder.button(text='Убрать выходную дату', callback_data='admin_action_remove_closed_date')
    builder.button(text='Список выходных дат', callback_data='admin_action_list_closed_dates')
    builder.button(text='Назад', callback_data='admin_menu_main')
    builder.adjust(1)
    return builder.as_markup()


def admin_settings_menu_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text='Изменить адрес', callback_data='admin_action_set_address')
    builder.button(text='Интервал слотов', callback_data='admin_action_set_slot_interval')
    builder.button(text='Добавить демо-данные', callback_data='admin_action_seed_demo')
    builder.button(text='Назад', callback_data='admin_menu_main')
    builder.adjust(1)
    return builder.as_markup()


def admin_after_action_kb(section_callback: str | None = None, section_text: str = 'Вернуться в раздел'):
    builder = InlineKeyboardBuilder()
    if section_callback and section_callback != 'admin_menu_main':
        builder.button(text=section_text, callback_data=section_callback)
    builder.button(text='Админка', callback_data='admin_menu_main')
    builder.adjust(1)
    return builder.as_markup()


def admin_cancel_kb(*, with_skip: bool = False, skip_text: str = ADMIN_SKIP_TEXT) -> ReplyKeyboardMarkup:
    keyboard = []
    if with_skip:
        keyboard.append([KeyboardButton(text=skip_text)])
    keyboard.append([KeyboardButton(text=ADMIN_CANCEL_TEXT)])
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True, one_time_keyboard=True)


def parse_admin_date(value: str) -> date:
    """Парсит дату в форматах YYYY-MM-DD или DD.MM.YYYY."""
    try:
        return date.fromisoformat(value)
    except ValueError:
        return datetime.strptime(value, '%d.%m.%Y').date()


def parse_time_range(value: str) -> tuple[time, time]:
    """Парсит диапазон времени ЧЧ:ММ-ЧЧ:ММ или ЧЧ:ММ ЧЧ:ММ."""
    cleaned = value.replace('—', '-').replace('–', '-').strip()
    if '-' in cleaned:
        start_raw, end_raw = cleaned.split('-', maxsplit=1)
    else:
        parts = cleaned.split()
        if len(parts) != 2:
            raise ValueError('Введите время в формате 10:00-20:00')
        start_raw, end_raw = parts
    return time.fromisoformat(start_raw.strip()), time.fromisoformat(end_raw.strip())


def parse_callback_int(data: str | None, prefix: str) -> int | None:
    if not data or not data.startswith(prefix):
        return None
    raw_value = data.removeprefix(prefix)
    if not raw_value.isdigit():
        return None
    return int(raw_value)


def parse_callback_date(data: str | None, prefix: str) -> date | None:
    if not data or not data.startswith(prefix):
        return None
    try:
        return date.fromisoformat(data.removeprefix(prefix))
    except ValueError:
        return None


def parse_callback_action(data: str | None, prefix: str, allowed_actions: set[str]) -> str | None:
    if not data or not data.startswith(prefix):
        return None
    action = data.removeprefix(prefix)
    if action not in allowed_actions:
        return None
    return action


def parse_slot_time(value: str | None) -> time | None:
    if not value:
        return None
    try:
        parsed_time = time.fromisoformat(value)
    except ValueError:
        return None
    if parsed_time.second or parsed_time.microsecond or parsed_time.tzinfo is not None:
        return None
    return parsed_time.replace(second=0, microsecond=0)


def parse_callback_slot(data: str | None, prefix: str) -> time | None:
    if not data or not data.startswith(prefix):
        return None
    return parse_slot_time(data.removeprefix(prefix))


async def answer_invalid_admin_callback(callback: types.CallbackQuery, text: str = INVALID_ADMIN_CALLBACK_TEXT):
    await callback.answer(text, show_alert=True)


async def answer_repeated_admin_action(callback: types.CallbackQuery):
    await callback.answer('Это действие уже обработано. Откройте раздел заново.', show_alert=True)


async def answer_unmatched_admin_callback(callback: types.CallbackQuery, state: FSMContext):
    current_state = await state.get_state()
    if current_state:
        await callback.answer(
            'Эта кнопка не относится к текущему шагу. Завершите диалог или нажмите /cancel.',
            show_alert=True,
        )
        return

    await callback.answer('Кнопка устарела. Откройте нужный раздел заново.', show_alert=True)
    if not callback.message:
        return
    try:
        await callback.message.edit_text(
            'Кнопка устарела. Откройте нужный раздел заново.',
            reply_markup=admin_after_action_kb(),
        )
    except TelegramBadRequest:
        await callback.message.answer('Админка', reply_markup=admin_main_menu_kb())


def services_selection_kb(services, selected_ids: set[int]):
    builder = InlineKeyboardBuilder()
    for service in services:
        marker = '✅' if service.id in selected_ids else '☐'
        builder.button(
            text=f'{marker} {service.name} ({service.duration} мин)',
            callback_data=f'admin_master_toggle_{service.id}',
        )
    builder.button(text='Готово', callback_data='admin_master_done')
    builder.button(text='Отмена', callback_data='admin_cancel')
    builder.adjust(1)
    return builder.as_markup()


def services_list_kb(services, prefix: str):
    builder = InlineKeyboardBuilder()
    for service in services:
        status = '🟢' if service.is_active else '⚪'
        builder.button(
            text=f'{status} {service.name} ({service.duration} мин)',
            callback_data=f'{prefix}_{service.id}',
        )
    builder.button(text='Отмена', callback_data='admin_cancel')
    builder.adjust(1)
    return builder.as_markup()


def masters_kb(masters, prefix: str):
    builder = InlineKeyboardBuilder()
    for master in masters:
        status = '' if master.is_active else '⚪ '
        builder.button(text=f'{status}{master.full_name}', callback_data=f'{prefix}_{master.id}')
    builder.button(text='Отмена', callback_data='admin_cancel')
    builder.adjust(1)
    return builder.as_markup()


def days_kb(prefix: str):
    builder = InlineKeyboardBuilder()
    for day_number, day_name in DAYS:
        builder.button(text=day_name, callback_data=f'{prefix}_{day_number}')
    builder.button(text='Отмена', callback_data='admin_cancel')
    builder.adjust(4)
    return builder.as_markup()


def schedule_action_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text='Рабочий день', callback_data='admin_schedule_action_work')
    builder.button(text='Выходной', callback_data='admin_schedule_action_off')
    builder.button(text='Отмена', callback_data='admin_cancel')
    builder.adjust(1)
    return builder.as_markup()


def edit_service_action_kb(service_id: int, is_active: bool):
    builder = InlineKeyboardBuilder()
    builder.button(text='Изменить название', callback_data='admin_edit_service_action_name')
    builder.button(text='Изменить длительность', callback_data='admin_edit_service_action_duration')
    action_text = 'Отключить' if is_active else 'Включить'
    builder.button(text=action_text, callback_data='admin_edit_service_action_toggle')
    builder.button(text='Отмена', callback_data='admin_cancel')
    builder.adjust(1)
    return builder.as_markup()


def edit_master_action_kb(master_id: int, is_active: bool):
    builder = InlineKeyboardBuilder()
    builder.button(text='Изменить имя', callback_data='admin_edit_master_action_name')
    builder.button(text='Изменить описание', callback_data='admin_edit_master_action_description')
    builder.button(text='Изменить услуги', callback_data='admin_edit_master_action_services')
    action_text = 'Отключить' if is_active else 'Включить'
    builder.button(text=action_text, callback_data='admin_edit_master_action_toggle')
    builder.button(text='Отмена', callback_data='admin_cancel')
    builder.adjust(1)
    return builder.as_markup()


def closed_dates_kb(closed_dates):
    builder = InlineKeyboardBuilder()
    for item in closed_dates:
        label = item.date.strftime('%d.%m.%Y')
        if item.reason:
            label += f' — {item.reason}'
        builder.button(text=label, callback_data=f'admin_closed_remove_{item.date.isoformat()}')
    builder.button(text='Отмена', callback_data='admin_cancel')
    builder.adjust(1)
    return builder.as_markup()


def booking_list_kb(appointments):
    builder = InlineKeyboardBuilder()
    for appointment in appointments:
        label = (
            f'{appointment.date_time:%d.%m %H:%M} · '
            f'{appointment.service.name} · {appointment.client_name}'
        )
        builder.button(text=label, callback_data=f'admin_booking_pick_{appointment.id}')
    builder.button(text='Отмена', callback_data='admin_cancel')
    builder.adjust(1)
    return builder.as_markup()


def booking_action_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text='Перенести', callback_data='admin_booking_action_reschedule')
    builder.button(text='Отменить запись', callback_data='admin_booking_action_cancel')
    builder.button(text='Отмена', callback_data='admin_cancel')
    builder.adjust(1)
    return builder.as_markup()


def create_booking_confirm_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text='Создать запись', callback_data='admin_create_booking_confirm')
    builder.button(text='Отмена', callback_data='admin_cancel')
    builder.adjust(1)
    return builder.as_markup()


def booking_date_kb():
    builder = InlineKeyboardBuilder()
    today = date.today()
    for day_offset in range(DAYS_AHEAD):
        day = today + timedelta(days=day_offset)
        builder.button(
            text=day.strftime('%d.%m'),
            callback_data=f'admin_booking_date_{day.isoformat()}',
        )
    builder.button(text='Отмена', callback_data='admin_cancel')
    builder.adjust(4)
    return builder.as_markup()


def booking_slots_kb(slots: list[str]):
    builder = InlineKeyboardBuilder()
    for slot in slots:
        builder.button(text=slot, callback_data=f'admin_booking_slot_{slot}')
    builder.button(text='Отмена', callback_data='admin_cancel')
    builder.adjust(4)
    return builder.as_markup()


def slot_interval_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text='30 минут', callback_data='admin_settings_slot_interval_30')
    builder.button(text='60 минут', callback_data='admin_settings_slot_interval_60')
    builder.button(text='Отмена', callback_data='admin_cancel')
    builder.adjust(1)
    return builder.as_markup()


def format_salon_settings(settings: dict[str, str | int]) -> str:
    return (
        'Настройки салона:\n'
        f'Адрес: {settings["address"]}\n'
        f'Интервал слотов: {settings["slot_interval"]} мин'
    )


def format_seed_demo_result(summary: dict[str, int]) -> str:
    return (
        'Демо-салон готов.\n'
        f'Услуги: добавлено {summary["services_created"]}, обновлено {summary["services_updated"]}\n'
        f'Мастера: добавлено {summary["masters_created"]}, обновлено {summary["masters_updated"]}\n'
        f'Расписание: добавлено {summary["schedules_created"]}, обновлено {summary["schedules_updated"]}\n'
        f'Настройки: обновлено {summary["settings_updated"]}'
    )


def format_appointment_summary(appointment) -> str:
    text = (
        f'Запись #{appointment.id}\n'
        f'Дата: {appointment.date_time:%d.%m.%Y %H:%M}\n'
        f'Услуга: {appointment.service.name}\n'
        f'Мастер: {appointment.master.full_name}\n'
        f'Клиент: {appointment.client_name}\n'
        f'Телефон: {appointment.client_phone}'
    )
    if appointment.comment:
        text += f'\nКомментарий: {appointment.comment}'
    return text


async def send_admin_result(
    message: types.Message,
    text: str,
    *,
    section_callback: str | None = None,
    section_text: str = 'Вернуться в раздел',
    remove_reply_keyboard: bool = False,
):
    if remove_reply_keyboard:
        await message.answer(text, reply_markup=ReplyKeyboardRemove())
        await message.answer(
            'Что дальше?',
            reply_markup=admin_after_action_kb(section_callback, section_text),
        )
        return
    await message.answer(
        text,
        reply_markup=admin_after_action_kb(section_callback, section_text),
    )


async def finish_admin_action(
    message: types.Message,
    state: FSMContext,
    text: str,
    *,
    section_callback: str | None = None,
    section_text: str = 'Вернуться в раздел',
):
    await state.clear()
    await send_admin_result(
        message,
        text,
        section_callback=section_callback,
        section_text=section_text,
        remove_reply_keyboard=True,
    )


@admin_router.message(F.text == ADMIN_CANCEL_TEXT)
async def cancel_admin_message(message: types.Message, state: FSMContext):
    await state.clear()
    await send_admin_result(message, 'Настройка отменена.', remove_reply_keyboard=True)


@admin_router.message(Command('cancel'))
async def cancel_admin_command(message: types.Message, state: FSMContext):
    await state.clear()
    await send_admin_result(message, 'Настройка отменена.', remove_reply_keyboard=True)


@admin_router.callback_query(F.data == 'admin_cancel')
async def cancel_admin_callback(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text('Настройка отменена.', reply_markup=admin_after_action_kb())
    await callback.answer()


@admin_router.message(Command('admin'))
async def cmd_admin(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    await state.clear()
    if current_state:
        await message.answer('Текущий админский диалог закрыт.', reply_markup=ReplyKeyboardRemove())
    await message.answer('Админка', reply_markup=admin_main_menu_kb())


@admin_router.callback_query(F.data == 'admin_menu_main')
async def open_admin_main_menu(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text('Админка', reply_markup=admin_main_menu_kb())
    await callback.answer()


@admin_router.callback_query(F.data == 'admin_menu_services')
async def open_admin_services_menu(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text('Услуги', reply_markup=admin_services_menu_kb())
    await callback.answer()


@admin_router.callback_query(F.data == 'admin_menu_masters')
async def open_admin_masters_menu(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text('Мастера', reply_markup=admin_masters_menu_kb())
    await callback.answer()


@admin_router.callback_query(F.data == 'admin_menu_schedule')
async def open_admin_schedule_menu(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text('Расписание', reply_markup=admin_schedule_menu_kb())
    await callback.answer()


@admin_router.callback_query(F.data == 'admin_menu_bookings')
async def open_admin_bookings_menu(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text('Записи', reply_markup=admin_bookings_menu_kb())
    await callback.answer()


@admin_router.callback_query(F.data == 'admin_menu_closed_dates')
async def open_admin_closed_dates_menu(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text('Выходные', reply_markup=admin_closed_dates_menu_kb())
    await callback.answer()


@admin_router.callback_query(F.data == 'admin_menu_settings')
async def open_admin_settings_menu(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    async with async_session_maker() as session:
        settings = await get_salon_settings(session)
    await callback.message.edit_text(
        format_salon_settings(settings),
        reply_markup=admin_settings_menu_kb(),
    )
    await callback.answer()


@admin_router.callback_query(F.data == 'admin_action_add_service')
async def menu_add_service(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await cmd_add_service(callback.message, state)


@admin_router.callback_query(F.data == 'admin_action_edit_service')
async def menu_edit_service(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await cmd_edit_service(callback.message, state)


@admin_router.callback_query(F.data == 'admin_action_list_services')
async def menu_list_services(callback: types.CallbackQuery):
    await callback.answer()
    await cmd_list_services(callback.message)


@admin_router.callback_query(F.data == 'admin_action_add_master')
async def menu_add_master(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await cmd_add_master(callback.message, state)


@admin_router.callback_query(F.data == 'admin_action_edit_master')
async def menu_edit_master(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await cmd_edit_master(callback.message, state)


@admin_router.callback_query(F.data == 'admin_action_list_masters')
async def menu_list_masters(callback: types.CallbackQuery):
    await callback.answer()
    await cmd_list_masters(callback.message)


@admin_router.callback_query(F.data == 'admin_action_set_schedule')
async def menu_set_schedule(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await cmd_set_schedule(callback.message, state)


@admin_router.callback_query(F.data == 'admin_action_set_day_off')
async def menu_set_day_off(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await cmd_set_day_off(callback.message, state)


@admin_router.callback_query(F.data == 'admin_action_create_booking')
async def menu_create_booking(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await cmd_create_booking(callback.message, state)


@admin_router.callback_query(F.data == 'admin_action_manage_bookings')
async def menu_manage_bookings(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await cmd_manage_bookings(callback.message, state)


@admin_router.callback_query(F.data == 'admin_action_view_bookings')
async def menu_view_bookings(callback: types.CallbackQuery):
    await callback.answer()
    await cmd_view_bookings(callback.message)


@admin_router.callback_query(F.data == 'admin_action_add_closed_date')
async def menu_add_closed_date(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await cmd_add_closed_date(callback.message, state)


@admin_router.callback_query(F.data == 'admin_action_remove_closed_date')
async def menu_remove_closed_date(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await cmd_remove_closed_date(callback.message, state)


@admin_router.callback_query(F.data == 'admin_action_list_closed_dates')
async def menu_list_closed_dates(callback: types.CallbackQuery):
    await callback.answer()
    await cmd_list_closed_dates(callback.message)


@admin_router.callback_query(F.data == 'admin_action_set_address')
async def menu_set_salon_address(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text('Введите новый адрес салона:')
    await callback.message.answer('Для отмены нажмите кнопку.', reply_markup=admin_cancel_kb())
    await state.set_state(AdminSalonSettingsForm.waiting_for_address)
    await callback.answer()


@admin_router.callback_query(F.data == 'admin_action_set_slot_interval')
async def menu_set_slot_interval(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text('Выберите интервал между слотами:', reply_markup=slot_interval_kb())
    await state.set_state(AdminSalonSettingsForm.waiting_for_slot_interval)
    await callback.answer()


@admin_router.callback_query(F.data == 'admin_action_seed_demo')
async def menu_seed_demo(callback: types.CallbackQuery, state: FSMContext):
    async with callback_action_lock(callback, 'admin_seed_demo'):
        await state.clear()
        async with async_session_maker() as session:
            summary = await seed_demo_salon(session)
        await callback.message.edit_text(
            format_seed_demo_result(summary),
            reply_markup=admin_after_action_kb('admin_menu_settings', 'К настройкам'),
        )
        await callback.answer()


@admin_router.message(Command('salon_settings', 'settings'))
async def cmd_salon_settings(message: types.Message, state: FSMContext):
    await state.clear()
    async with async_session_maker() as session:
        settings = await get_salon_settings(session)
    await message.answer(format_salon_settings(settings), reply_markup=admin_settings_menu_kb())


@admin_router.message(Command('set_salon_address'))
async def cmd_set_salon_address(message: types.Message, state: FSMContext):
    parts = message.text.split(maxsplit=1)
    if len(parts) == 2:
        try:
            async with async_session_maker() as session:
                address = await update_salon_address(session, parts[1])
        except ValueError as error:
            await message.reply(f'Ошибка: {error}')
            return
        await send_admin_result(
            message,
            f'Адрес салона обновлён: {address}',
            section_callback='admin_menu_settings',
            section_text='К настройкам',
        )
        return

    await state.clear()
    await message.answer('Введите новый адрес салона:', reply_markup=admin_cancel_kb())
    await state.set_state(AdminSalonSettingsForm.waiting_for_address)


@admin_router.message(AdminSalonSettingsForm.waiting_for_address, F.text, ~F.text.startswith('/'))
async def process_salon_address(message: types.Message, state: FSMContext):
    try:
        async with async_session_maker() as session:
            address = await update_salon_address(session, message.text)
    except ValueError as error:
        await message.reply(f'Ошибка: {error}')
        return
    await finish_admin_action(
        message,
        state,
        f'Адрес салона обновлён: {address}',
        section_callback='admin_menu_settings',
        section_text='К настройкам',
    )


@admin_router.message(Command('set_slot_interval'))
async def cmd_set_slot_interval(message: types.Message, state: FSMContext):
    parts = message.text.split(maxsplit=1)
    if len(parts) == 2:
        try:
            async with async_session_maker() as session:
                interval = await update_slot_interval(session, parts[1])
        except ValueError as error:
            await message.reply(f'Ошибка: {error}')
            return
        await send_admin_result(
            message,
            f'Интервал слотов обновлён: {interval} мин.',
            section_callback='admin_menu_settings',
            section_text='К настройкам',
        )
        return

    await state.clear()
    await message.answer('Выберите интервал между слотами:', reply_markup=slot_interval_kb())
    await state.set_state(AdminSalonSettingsForm.waiting_for_slot_interval)


@admin_router.callback_query(
    AdminSalonSettingsForm.waiting_for_slot_interval,
    F.data.startswith('admin_settings_slot_interval_'),
)
async def choose_slot_interval(callback: types.CallbackQuery, state: FSMContext):
    async with callback_action_lock(callback, 'admin_set_slot_interval'):
        if not await is_expected_state(state, AdminSalonSettingsForm.waiting_for_slot_interval):
            await answer_repeated_admin_action(callback)
            return
        interval_raw = callback.data.removeprefix('admin_settings_slot_interval_')
        try:
            interval = validate_slot_interval(interval_raw)
            async with async_session_maker() as session:
                await update_slot_interval(session, interval)
        except ValueError as error:
            await callback.answer(str(error), show_alert=True)
            return
        await state.clear()
        await callback.message.edit_text(
            f'Интервал слотов обновлён: {interval} мин.',
            reply_markup=admin_after_action_kb('admin_menu_settings', 'К настройкам'),
        )
        await callback.answer()


@admin_router.message(Command('seed_demo'))
async def cmd_seed_demo(message: types.Message, state: FSMContext):
    await state.clear()
    async with async_session_maker() as session:
        summary = await seed_demo_salon(session)
    await send_admin_result(
        message,
        format_seed_demo_result(summary),
        section_callback='admin_menu_settings',
        section_text='К настройкам',
    )


@admin_router.message(Command('add_service'))
async def cmd_add_service(message: types.Message, state: FSMContext):
    args = message.text.split()
    if len(args) >= 3:
        try:
            duration = int(args[-1])
            name = ' '.join(args[1:-1])
            async with async_session_maker() as session:
                await add_service(session, name, duration)
        except ValueError as error:
            await message.reply(f'Ошибка: {error}')
            return
        await send_admin_result(
            message,
            f"Услуга '{name}' добавлена (длительность {duration} мин)",
            section_callback='admin_menu_services',
            section_text='К услугам',
        )
        return

    await state.clear()
    await message.answer('Введите название услуги:', reply_markup=admin_cancel_kb())
    await state.set_state(AdminServiceForm.waiting_for_name)


@admin_router.message(AdminServiceForm.waiting_for_name, F.text, ~F.text.startswith('/'))
async def process_service_name(message: types.Message, state: FSMContext):
    name = message.text.strip()
    if not name:
        await message.reply('Название услуги не может быть пустым.')
        return
    await state.update_data(name=name)
    await message.answer('Введите длительность услуги в минутах:', reply_markup=admin_cancel_kb())
    await state.set_state(AdminServiceForm.waiting_for_duration)


@admin_router.message(AdminServiceForm.waiting_for_duration, F.text, ~F.text.startswith('/'))
async def process_service_duration(message: types.Message, state: FSMContext):
    try:
        duration = int(message.text.strip())
    except ValueError:
        await message.reply('Длительность должна быть числом, например 45.')
        return
    data = await state.get_data()
    try:
        async with async_session_maker() as session:
            await add_service(session, data['name'], duration)
    except ValueError as error:
        await message.reply(f'Ошибка: {error}')
        return
    await finish_admin_action(
        message,
        state,
        f"Услуга '{data['name']}' добавлена ({duration} мин).",
        section_callback='admin_menu_services',
        section_text='К услугам',
    )


@admin_router.message(Command('edit_service'))
async def cmd_edit_service(message: types.Message, state: FSMContext):
    await state.clear()
    async with async_session_maker() as session:
        services = await get_services(session, active_only=False)
    if not services:
        await send_admin_result(
            message,
            'Услуги ещё не добавлены.',
            section_callback='admin_menu_services',
            section_text='К услугам',
        )
        return
    await message.answer(
        'Выберите услугу для редактирования:',
        reply_markup=services_list_kb(services, 'admin_edit_service'),
    )
    await state.set_state(AdminEditServiceForm.waiting_for_service)


@admin_router.callback_query(AdminEditServiceForm.waiting_for_service, F.data.startswith('admin_edit_service_'))
async def choose_edit_service(callback: types.CallbackQuery, state: FSMContext):
    service_id = parse_callback_int(callback.data, 'admin_edit_service_')
    if service_id is None:
        await answer_invalid_admin_callback(callback)
        return
    async with async_session_maker() as session:
        service = await get_service(session, service_id)
    if not service:
        await callback.answer('Услуга не найдена.', show_alert=True)
        return
    await state.update_data(service_id=service_id, service_is_active=bool(service.is_active))
    status = 'активна' if service.is_active else 'отключена'
    await callback.message.edit_text(
        f'Услуга: {service.name} ({service.duration} мин), статус: {status}.',
        reply_markup=edit_service_action_kb(service_id, bool(service.is_active)),
    )
    await state.set_state(AdminEditServiceForm.waiting_for_action)
    await callback.answer()


@admin_router.callback_query(AdminEditServiceForm.waiting_for_action, F.data.startswith('admin_edit_service_action_'))
async def choose_edit_service_action(callback: types.CallbackQuery, state: FSMContext):
    async with callback_action_lock(callback, 'admin_edit_service_action'):
        if not await is_expected_state(state, AdminEditServiceForm.waiting_for_action):
            await answer_repeated_admin_action(callback)
            return
        action = parse_callback_action(
            callback.data,
            'admin_edit_service_action_',
            {'name', 'duration', 'toggle'},
        )
        if action is None:
            await answer_invalid_admin_callback(callback)
            return
        data = await state.get_data()
        if action == 'name':
            await callback.message.edit_text('Введите новое название услуги:')
            await callback.message.answer('Для отмены нажмите кнопку.', reply_markup=admin_cancel_kb())
            await state.set_state(AdminEditServiceForm.waiting_for_name)
        elif action == 'duration':
            await callback.message.edit_text('Введите новую длительность услуги в минутах:')
            await callback.message.answer('Для отмены нажмите кнопку.', reply_markup=admin_cancel_kb())
            await state.set_state(AdminEditServiceForm.waiting_for_duration)
        elif action == 'toggle':
            try:
                async with async_session_maker() as session:
                    service = await set_service_active(
                        session,
                        data['service_id'],
                        not data.get('service_is_active', True),
                    )
            except ValueError as error:
                await callback.answer(str(error), show_alert=True)
                return
            await state.clear()
            status = 'включена' if service.is_active else 'отключена'
            await callback.message.edit_text(
                f"Услуга '{service.name}' {status}.",
                reply_markup=admin_after_action_kb('admin_menu_services', 'К услугам'),
            )
        await callback.answer()


@admin_router.message(AdminEditServiceForm.waiting_for_name, F.text, ~F.text.startswith('/'))
async def process_edit_service_name(message: types.Message, state: FSMContext):
    data = await state.get_data()
    try:
        async with async_session_maker() as session:
            service = await update_service(session, data['service_id'], name=message.text)
    except ValueError as error:
        await message.reply(f'Ошибка: {error}')
        return
    await finish_admin_action(
        message,
        state,
        f"Название услуги обновлено: '{service.name}'.",
        section_callback='admin_menu_services',
        section_text='К услугам',
    )


@admin_router.message(AdminEditServiceForm.waiting_for_duration, F.text, ~F.text.startswith('/'))
async def process_edit_service_duration(message: types.Message, state: FSMContext):
    try:
        duration = int(message.text.strip())
    except ValueError:
        await message.reply('Длительность должна быть числом, например 45.')
        return
    data = await state.get_data()
    try:
        async with async_session_maker() as session:
            service = await update_service(session, data['service_id'], duration=duration)
    except ValueError as error:
        await message.reply(f'Ошибка: {error}')
        return
    await finish_admin_action(
        message,
        state,
        f"Длительность услуги '{service.name}' обновлена: {duration} мин.",
        section_callback='admin_menu_services',
        section_text='К услугам',
    )


@admin_router.message(Command('add_master'))
async def cmd_add_master(message: types.Message, state: FSMContext):
    try:
        parts = shlex.split(message.text)
        if len(parts) == 4:
            _, full_name, description, ids_str = parts
            service_ids = [int(x) for x in ids_str.split(',') if x.strip()]
            async with async_session_maker() as session:
                await add_master(session, full_name, description, service_ids)
            await send_admin_result(
                message,
                f"Мастер '{full_name}' добавлен с услугами {service_ids}",
                section_callback='admin_menu_masters',
                section_text='К мастерам',
            )
            return
        if len(parts) != 1:
            raise ValueError
    except Exception as error:
        await message.reply(
            'Формат быстрого добавления: /add_master "Имя мастера" "Описание" id_услуги1,id_услуги2\n'
            f'Ошибка: {error}'
        )
        return

    await state.clear()
    async with async_session_maker() as session:
        services = await get_services(session)
    if not services:
        await send_admin_result(
            message,
            'Сначала добавьте хотя бы одну услугу через /add_service.',
            section_callback='admin_menu_services',
            section_text='К услугам',
        )
        return
    await message.answer('Введите имя мастера:', reply_markup=admin_cancel_kb())
    await state.set_state(AdminMasterForm.waiting_for_name)


@admin_router.message(AdminMasterForm.waiting_for_name, F.text, ~F.text.startswith('/'))
async def process_master_name(message: types.Message, state: FSMContext):
    full_name = message.text.strip()
    if not full_name:
        await message.reply('Имя мастера не может быть пустым.')
        return
    await state.update_data(full_name=full_name)
    await message.answer(
        'Введите краткое описание мастера или нажмите «Пропустить»:',
        reply_markup=admin_cancel_kb(with_skip=True),
    )
    await state.set_state(AdminMasterForm.waiting_for_description)


@admin_router.message(AdminMasterForm.waiting_for_description, F.text, ~F.text.startswith('/'))
async def process_master_description(message: types.Message, state: FSMContext):
    description = '' if message.text == ADMIN_SKIP_TEXT else message.text.strip()
    await state.update_data(description=description, selected_service_ids=[])
    async with async_session_maker() as session:
        services = await get_services(session)
    await message.answer('Выберите услуги мастера:', reply_markup=ReplyKeyboardRemove())
    await message.answer(
        'Нажимайте на услуги, затем «Готово».',
        reply_markup=services_selection_kb(services, set()),
    )
    await state.set_state(AdminMasterForm.waiting_for_services)


@admin_router.callback_query(AdminMasterForm.waiting_for_services, F.data.startswith('admin_master_toggle_'))
async def toggle_master_service(callback: types.CallbackQuery, state: FSMContext):
    service_id = parse_callback_int(callback.data, 'admin_master_toggle_')
    if service_id is None:
        await answer_invalid_admin_callback(callback)
        return
    data = await state.get_data()
    selected_ids = set(data.get('selected_service_ids', []))
    if service_id in selected_ids:
        selected_ids.remove(service_id)
    else:
        selected_ids.add(service_id)
    await state.update_data(selected_service_ids=list(selected_ids))
    async with async_session_maker() as session:
        services = await get_services(session)
    await callback.message.edit_reply_markup(reply_markup=services_selection_kb(services, selected_ids))
    await callback.answer()


@admin_router.callback_query(AdminMasterForm.waiting_for_services, F.data == 'admin_master_done')
async def finish_master_dialog(callback: types.CallbackQuery, state: FSMContext):
    async with callback_action_lock(callback, 'admin_finish_master'):
        if not await is_expected_state(state, AdminMasterForm.waiting_for_services):
            await answer_repeated_admin_action(callback)
            return
        data = await state.get_data()
        service_ids = data.get('selected_service_ids', [])
        if not service_ids:
            await callback.answer('Выберите хотя бы одну услугу.', show_alert=True)
            return
        try:
            async with async_session_maker() as session:
                await add_master(session, data['full_name'], data['description'], service_ids)
        except ValueError as error:
            await callback.answer(str(error), show_alert=True)
            return
        await state.clear()
        await callback.message.edit_text(
            f"Мастер '{data['full_name']}' добавлен. Услуги: {', '.join(map(str, service_ids))}.",
            reply_markup=admin_after_action_kb('admin_menu_masters', 'К мастерам'),
        )
        await callback.answer()


@admin_router.message(Command('edit_master'))
async def cmd_edit_master(message: types.Message, state: FSMContext):
    await state.clear()
    async with async_session_maker() as session:
        masters = await get_masters(session, active_only=False)
    if not masters:
        await send_admin_result(
            message,
            'Мастера ещё не добавлены.',
            section_callback='admin_menu_masters',
            section_text='К мастерам',
        )
        return
    await message.answer('Выберите мастера для редактирования:', reply_markup=masters_kb(masters, 'admin_edit_master'))
    await state.set_state(AdminEditMasterForm.waiting_for_master)


@admin_router.callback_query(AdminEditMasterForm.waiting_for_master, F.data.startswith('admin_edit_master_'))
async def choose_edit_master(callback: types.CallbackQuery, state: FSMContext):
    master_id = parse_callback_int(callback.data, 'admin_edit_master_')
    if master_id is None:
        await answer_invalid_admin_callback(callback)
        return
    async with async_session_maker() as session:
        master = await get_master(session, master_id)
    if not master:
        await callback.answer('Мастер не найден.', show_alert=True)
        return
    await state.update_data(master_id=master_id, master_is_active=bool(master.is_active))
    status = 'активен' if master.is_active else 'отключён'
    services_text = ', '.join(service.name for service in master.services) or 'услуги не выбраны'
    description = master.description or 'без описания'
    await callback.message.edit_text(
        f'Мастер: {master.full_name}\n'
        f'Описание: {description}\n'
        f'Услуги: {services_text}\n'
        f'Статус: {status}.',
        reply_markup=edit_master_action_kb(master_id, bool(master.is_active)),
    )
    await state.set_state(AdminEditMasterForm.waiting_for_action)
    await callback.answer()


@admin_router.callback_query(AdminEditMasterForm.waiting_for_action, F.data.startswith('admin_edit_master_action_'))
async def choose_edit_master_action(callback: types.CallbackQuery, state: FSMContext):
    async with callback_action_lock(callback, 'admin_edit_master_action'):
        if not await is_expected_state(state, AdminEditMasterForm.waiting_for_action):
            await answer_repeated_admin_action(callback)
            return
        action = parse_callback_action(
            callback.data,
            'admin_edit_master_action_',
            {'name', 'description', 'services', 'toggle'},
        )
        if action is None:
            await answer_invalid_admin_callback(callback)
            return
        data = await state.get_data()
        if action == 'name':
            await callback.message.edit_text('Введите новое имя мастера:')
            await callback.message.answer('Для отмены нажмите кнопку.', reply_markup=admin_cancel_kb())
            await state.set_state(AdminEditMasterForm.waiting_for_name)
        elif action == 'description':
            await callback.message.edit_text('Введите новое описание мастера или нажмите «Пропустить»:')
            await callback.message.answer('Для отмены нажмите кнопку.', reply_markup=admin_cancel_kb(with_skip=True))
            await state.set_state(AdminEditMasterForm.waiting_for_description)
        elif action == 'services':
            async with async_session_maker() as session:
                master = await get_master(session, data['master_id'])
                services = await get_services(session)
            if not services:
                await callback.answer('Сначала добавьте активные услуги.', show_alert=True)
                return
            selected_ids = {service.id for service in master.services if service.is_active}
            await state.update_data(selected_service_ids=list(selected_ids))
            await callback.message.edit_text(
                'Выберите услуги мастера:',
                reply_markup=services_selection_kb(services, selected_ids),
            )
            await state.set_state(AdminEditMasterForm.waiting_for_services)
        elif action == 'toggle':
            try:
                async with async_session_maker() as session:
                    master = await set_master_active(
                        session,
                        data['master_id'],
                        not data.get('master_is_active', True),
                    )
            except ValueError as error:
                await callback.answer(str(error), show_alert=True)
                return
            await state.clear()
            status = 'включён' if master.is_active else 'отключён'
            await callback.message.edit_text(
                f"Мастер '{master.full_name}' {status}.",
                reply_markup=admin_after_action_kb('admin_menu_masters', 'К мастерам'),
            )
        await callback.answer()


@admin_router.message(AdminEditMasterForm.waiting_for_name, F.text, ~F.text.startswith('/'))
async def process_edit_master_name(message: types.Message, state: FSMContext):
    data = await state.get_data()
    try:
        async with async_session_maker() as session:
            master = await update_master(session, data['master_id'], full_name=message.text)
    except ValueError as error:
        await message.reply(f'Ошибка: {error}')
        return
    await finish_admin_action(
        message,
        state,
        f"Имя мастера обновлено: '{master.full_name}'.",
        section_callback='admin_menu_masters',
        section_text='К мастерам',
    )


@admin_router.message(AdminEditMasterForm.waiting_for_description, F.text, ~F.text.startswith('/'))
async def process_edit_master_description(message: types.Message, state: FSMContext):
    description = '' if message.text == ADMIN_SKIP_TEXT else message.text
    data = await state.get_data()
    try:
        async with async_session_maker() as session:
            master = await update_master(session, data['master_id'], description=description)
    except ValueError as error:
        await message.reply(f'Ошибка: {error}')
        return
    text = master.description or 'без описания'
    await finish_admin_action(
        message,
        state,
        f"Описание мастера обновлено: {text}.",
        section_callback='admin_menu_masters',
        section_text='К мастерам',
    )


@admin_router.callback_query(AdminEditMasterForm.waiting_for_services, F.data.startswith('admin_master_toggle_'))
async def toggle_edit_master_service(callback: types.CallbackQuery, state: FSMContext):
    service_id = parse_callback_int(callback.data, 'admin_master_toggle_')
    if service_id is None:
        await answer_invalid_admin_callback(callback)
        return
    data = await state.get_data()
    selected_ids = set(data.get('selected_service_ids', []))
    if service_id in selected_ids:
        selected_ids.remove(service_id)
    else:
        selected_ids.add(service_id)
    await state.update_data(selected_service_ids=list(selected_ids))
    async with async_session_maker() as session:
        services = await get_services(session)
    await callback.message.edit_reply_markup(reply_markup=services_selection_kb(services, selected_ids))
    await callback.answer()


@admin_router.callback_query(AdminEditMasterForm.waiting_for_services, F.data == 'admin_master_done')
async def finish_edit_master_services(callback: types.CallbackQuery, state: FSMContext):
    async with callback_action_lock(callback, 'admin_finish_edit_master_services'):
        if not await is_expected_state(state, AdminEditMasterForm.waiting_for_services):
            await answer_repeated_admin_action(callback)
            return
        data = await state.get_data()
        service_ids = data.get('selected_service_ids', [])
        if not service_ids:
            await callback.answer('Выберите хотя бы одну услугу.', show_alert=True)
            return
        try:
            async with async_session_maker() as session:
                await set_master_services(session, data['master_id'], service_ids)
        except ValueError as error:
            await callback.answer(str(error), show_alert=True)
            return
        await state.clear()
        await callback.message.edit_text(
            f"Услуги мастера обновлены: {', '.join(map(str, service_ids))}.",
            reply_markup=admin_after_action_kb('admin_menu_masters', 'К мастерам'),
        )
        await callback.answer()


@admin_router.message(Command('list_services'))
async def cmd_list_services(message: types.Message):
    async with async_session_maker() as session:
        services = await get_services(session, active_only=False)
    if not services:
        await send_admin_result(
            message,
            'Услуги ещё не добавлены.',
            section_callback='admin_menu_services',
            section_text='К услугам',
        )
        return
    lines = ['Список услуг:']
    for service in services:
        status = 'активна' if service.is_active else 'отключена'
        lines.append(f'{service.id}. {service.name} ({service.duration} мин) — {status}')
    text = '\n'.join(lines)
    await send_admin_result(message, text, section_callback='admin_menu_services', section_text='К услугам')


@admin_router.message(Command('list_masters'))
async def cmd_list_masters(message: types.Message):
    async with async_session_maker() as session:
        masters = await get_masters(session, active_only=False)
    if not masters:
        await send_admin_result(
            message,
            'Мастера ещё не добавлены.',
            section_callback='admin_menu_masters',
            section_text='К мастерам',
        )
        return
    lines = ['Список мастеров:']
    for master in masters:
        service_ids = ','.join(str(service.id) for service in master.services) or 'все услуги'
        description = f' — {master.description}' if master.description else ''
        status = 'активен' if master.is_active else 'отключён'
        lines.append(f'{master.id}. {master.full_name}{description}; услуги: {service_ids}; {status}')
    await send_admin_result(
        message,
        '\n'.join(lines),
        section_callback='admin_menu_masters',
        section_text='К мастерам',
    )


@admin_router.message(Command('set_schedule'))
async def cmd_set_schedule(message: types.Message, state: FSMContext):
    parts = message.text.split()
    if len(parts) >= 5:
        try:
            master_id = int(parts[1])
            day_of_week = int(parts[2])
            start_time = time.fromisoformat(parts[3])
            end_time = time.fromisoformat(parts[4])
            lunch_start = None
            lunch_end = None
            if len(parts) >= 7:
                lunch_start = time.fromisoformat(parts[5])
                lunch_end = time.fromisoformat(parts[6])
            async with async_session_maker() as session:
                await set_master_schedule(
                    session, master_id, day_of_week, start_time, end_time, lunch_start, lunch_end
                )
            await send_admin_result(
                message,
                f'Расписание для мастера {master_id} обновлено.',
                section_callback='admin_menu_schedule',
                section_text='К расписанию',
            )
            return
        except Exception as error:
            await message.reply(f'Ошибка: {error}. Проверьте формат.')
            return

    await state.clear()
    async with async_session_maker() as session:
        masters = await get_masters(session)
    if not masters:
        await send_admin_result(
            message,
            'Сначала добавьте хотя бы одного мастера через /add_master.',
            section_callback='admin_menu_masters',
            section_text='К мастерам',
        )
        return
    await message.answer('Выберите мастера:', reply_markup=masters_kb(masters, 'admin_schedule_master'))
    await state.set_state(AdminScheduleForm.waiting_for_master)


@admin_router.callback_query(AdminScheduleForm.waiting_for_master, F.data.startswith('admin_schedule_master_'))
async def choose_schedule_master(callback: types.CallbackQuery, state: FSMContext):
    master_id = parse_callback_int(callback.data, 'admin_schedule_master_')
    if master_id is None:
        await answer_invalid_admin_callback(callback)
        return
    await state.update_data(master_id=master_id)
    await callback.message.edit_text('Выберите день недели:', reply_markup=days_kb('admin_schedule_day'))
    await state.set_state(AdminScheduleForm.waiting_for_day)
    await callback.answer()


@admin_router.callback_query(AdminScheduleForm.waiting_for_day, F.data.startswith('admin_schedule_day_'))
async def choose_schedule_day(callback: types.CallbackQuery, state: FSMContext):
    day_of_week = parse_callback_int(callback.data, 'admin_schedule_day_')
    if day_of_week not in dict(DAYS):
        await answer_invalid_admin_callback(callback)
        return
    await state.update_data(day_of_week=day_of_week)
    day_name = dict(DAYS)[day_of_week]
    await callback.message.edit_text(
        f'{day_name}: это рабочий день или выходной?',
        reply_markup=schedule_action_kb(),
    )
    await state.set_state(AdminScheduleForm.waiting_for_action)
    await callback.answer()


@admin_router.callback_query(AdminScheduleForm.waiting_for_action, F.data.startswith('admin_schedule_action_'))
async def choose_schedule_action(callback: types.CallbackQuery, state: FSMContext):
    async with callback_action_lock(callback, 'admin_schedule_action'):
        if not await is_expected_state(state, AdminScheduleForm.waiting_for_action):
            await answer_repeated_admin_action(callback)
            return
        action = parse_callback_action(callback.data, 'admin_schedule_action_', {'work', 'off'})
        if action is None:
            await answer_invalid_admin_callback(callback)
            return
        data = await state.get_data()
        if action == 'off':
            try:
                async with async_session_maker() as session:
                    await set_master_day_off(session, data['master_id'], data['day_of_week'])
            except ValueError as error:
                await callback.answer(str(error), show_alert=True)
                return
            await state.clear()
            await callback.message.edit_text(
                'Выходной день сохранён.',
                reply_markup=admin_after_action_kb('admin_menu_schedule', 'К расписанию'),
            )
            await callback.answer()
            return

        await callback.message.edit_text('Введите рабочие часы в формате 10:00-20:00.')
        await callback.message.answer('Можно также написать: 10:00 20:00', reply_markup=admin_cancel_kb())
        await state.set_state(AdminScheduleForm.waiting_for_work_hours)
        await callback.answer()


@admin_router.message(AdminScheduleForm.waiting_for_work_hours, F.text, ~F.text.startswith('/'))
async def process_schedule_work_hours(message: types.Message, state: FSMContext):
    try:
        start_time, end_time = parse_time_range(message.text)
    except ValueError as error:
        await message.reply(str(error))
        return
    await state.update_data(
        start_time=start_time.isoformat(timespec='minutes'),
        end_time=end_time.isoformat(timespec='minutes'),
    )
    await message.answer(
        'Введите обед в формате 14:00-15:00 или нажмите «Пропустить»:',
        reply_markup=admin_cancel_kb(with_skip=True),
    )
    await state.set_state(AdminScheduleForm.waiting_for_lunch)


@admin_router.message(AdminScheduleForm.waiting_for_lunch, F.text, ~F.text.startswith('/'))
async def process_schedule_lunch(message: types.Message, state: FSMContext):
    lunch_start = None
    lunch_end = None
    if message.text != ADMIN_SKIP_TEXT:
        try:
            lunch_start, lunch_end = parse_time_range(message.text)
        except ValueError as error:
            await message.reply(str(error))
            return

    data = await state.get_data()
    start_time = time.fromisoformat(data['start_time'])
    end_time = time.fromisoformat(data['end_time'])
    try:
        async with async_session_maker() as session:
            await set_master_schedule(
                session,
                data['master_id'],
                data['day_of_week'],
                start_time,
                end_time,
                lunch_start,
                lunch_end,
            )
    except ValueError as error:
        await message.reply(f'Ошибка: {error}')
        return

    day_name = dict(DAYS)[data['day_of_week']]
    lunch_text = 'без обеда' if lunch_start is None else f'обед {lunch_start:%H:%M}-{lunch_end:%H:%M}'
    await finish_admin_action(
        message,
        state,
        f'Расписание сохранено: {day_name}, {start_time:%H:%M}-{end_time:%H:%M}, {lunch_text}.',
        section_callback='admin_menu_schedule',
        section_text='К расписанию',
    )


@admin_router.message(Command('set_day_off'))
async def cmd_set_day_off(message: types.Message, state: FSMContext):
    parts = message.text.split()
    if len(parts) == 3:
        try:
            master_id = int(parts[1])
            day_of_week = int(parts[2])
            async with async_session_maker() as session:
                await set_master_day_off(session, master_id, day_of_week)
        except ValueError as error:
            await message.reply(f'Ошибка: {error}')
            return
        await send_admin_result(
            message,
            f'День недели {day_of_week} отмечен как выходной для мастера {master_id}.',
            section_callback='admin_menu_schedule',
            section_text='К расписанию',
        )
        return

    await cmd_set_schedule(message, state)


@admin_router.message(Command('view_bookings'))
async def cmd_view_bookings(message: types.Message):
    async with async_session_maker() as session:
        appointments = await get_future_appointments(session)
    if not appointments:
        await send_admin_result(
            message,
            'Будущих записей нет.',
            section_callback='admin_menu_bookings',
            section_text='К записям',
        )
        return
    response_lines = ['Предстоящие записи:']
    for appointment in appointments:
        response_lines.append(
            f"• {appointment.date_time.strftime('%d.%m.%Y %H:%M')} — "
            f"{appointment.service.name} у {appointment.master.full_name}, "
            f"клиент: {appointment.client_name} ({appointment.client_phone})"
        )
        if appointment.comment:
            response_lines.append(f'  Комментарий: {appointment.comment}')
    await send_admin_result(
        message,
        '\n'.join(response_lines),
        section_callback='admin_menu_bookings',
        section_text='К записям',
    )


@admin_router.message(Command('create_booking'))
async def cmd_create_booking(message: types.Message, state: FSMContext):
    await state.clear()
    async with async_session_maker() as session:
        services = await get_services(session)
    if not services:
        await send_admin_result(
            message,
            'Нет активных услуг. Сначала добавьте или включите услугу.',
            section_callback='admin_menu_services',
            section_text='К услугам',
        )
        return
    await message.answer('Выберите услугу:', reply_markup=services_list_kb(services, 'admin_create_service'))
    await state.set_state(AdminCreateBookingForm.waiting_for_service)


@admin_router.callback_query(
    AdminCreateBookingForm.waiting_for_service,
    F.data.startswith('admin_create_service_'),
)
async def choose_manual_booking_service(callback: types.CallbackQuery, state: FSMContext):
    service_id = parse_callback_int(callback.data, 'admin_create_service_')
    if service_id is None:
        await answer_invalid_admin_callback(callback)
        return
    async with async_session_maker() as session:
        service = await get_service(session, service_id)
        masters = await get_masters_by_service(session, service_id)
    if not service or not service.is_active:
        await callback.answer('Услуга не найдена или отключена.', show_alert=True)
        return
    if not masters:
        await callback.answer('Нет активных мастеров для этой услуги.', show_alert=True)
        return
    await state.update_data(
        service_id=service.id,
        service_name=service.name,
        service_duration=service.duration,
    )
    await callback.message.edit_text('Выберите мастера:', reply_markup=masters_kb(masters, 'admin_create_master'))
    await state.set_state(AdminCreateBookingForm.waiting_for_master)
    await callback.answer()


@admin_router.callback_query(
    AdminCreateBookingForm.waiting_for_master,
    F.data.startswith('admin_create_master_'),
)
async def choose_manual_booking_master(callback: types.CallbackQuery, state: FSMContext):
    master_id = parse_callback_int(callback.data, 'admin_create_master_')
    if master_id is None:
        await answer_invalid_admin_callback(callback)
        return
    async with async_session_maker() as session:
        master = await get_master(session, master_id)
    if not master or not master.is_active:
        await callback.answer('Мастер не найден или отключён.', show_alert=True)
        return
    await state.update_data(master_id=master.id, master_name=master.full_name)
    await callback.message.edit_text('Выберите дату:', reply_markup=booking_date_kb())
    await state.set_state(AdminCreateBookingForm.waiting_for_date)
    await callback.answer()


@admin_router.callback_query(
    AdminCreateBookingForm.waiting_for_date,
    F.data.startswith('admin_booking_date_'),
)
async def choose_manual_booking_date(callback: types.CallbackQuery, state: FSMContext):
    chosen_date = parse_callback_date(callback.data, 'admin_booking_date_')
    if chosen_date is None:
        await answer_invalid_admin_callback(callback)
        return
    data = await state.get_data()
    async with async_session_maker() as session:
        free_slots = await get_free_slots(session, data['master_id'], data['service_id'], chosen_date)
    if not free_slots:
        await callback.message.edit_text(
            'На эту дату нет свободного времени. Выберите другую дату:',
            reply_markup=booking_date_kb(),
        )
        await callback.answer()
        return
    await state.update_data(chosen_date=chosen_date.isoformat())
    await callback.message.edit_text('Выберите время:', reply_markup=booking_slots_kb(free_slots))
    await state.set_state(AdminCreateBookingForm.waiting_for_time)
    await callback.answer()


@admin_router.callback_query(
    AdminCreateBookingForm.waiting_for_time,
    F.data.startswith('admin_booking_slot_'),
)
async def choose_manual_booking_time(callback: types.CallbackQuery, state: FSMContext):
    async with callback_action_lock(callback, 'admin_choose_manual_booking_time'):
        if not await is_expected_state(state, AdminCreateBookingForm.waiting_for_time):
            await answer_repeated_admin_action(callback)
            return
        slot_time = parse_callback_slot(callback.data, 'admin_booking_slot_')
        if slot_time is None:
            await answer_invalid_admin_callback(callback)
            return
        slot = slot_time.isoformat(timespec='minutes')
        await state.update_data(slot_time=slot)
        await callback.message.edit_text(f'Выбрано время: {slot}.')
        await callback.message.answer('Введите имя клиента:', reply_markup=admin_cancel_kb())
        await state.set_state(AdminCreateBookingForm.waiting_for_name)
        await callback.answer()


@admin_router.message(AdminCreateBookingForm.waiting_for_name, F.text, ~F.text.startswith('/'))
async def process_manual_booking_name(message: types.Message, state: FSMContext):
    name = message.text.strip()
    is_valid, error_message = validate_name(name)
    if not is_valid:
        await message.reply(error_message)
        return
    await state.update_data(client_name=name)
    await message.answer('Введите телефон клиента:', reply_markup=admin_cancel_kb())
    await state.set_state(AdminCreateBookingForm.waiting_for_phone)


@admin_router.message(AdminCreateBookingForm.waiting_for_phone, F.text, ~F.text.startswith('/'))
async def process_manual_booking_phone(message: types.Message, state: FSMContext):
    phone = message.text.strip()
    is_valid, error_message = validate_phone(phone)
    if not is_valid:
        await message.reply(error_message)
        return
    await state.update_data(client_phone=normalize_phone(phone))
    await message.answer(
        'Введите комментарий к записи или нажмите «Пропустить»:',
        reply_markup=admin_cancel_kb(with_skip=True),
    )
    await state.set_state(AdminCreateBookingForm.waiting_for_comment)


@admin_router.message(AdminCreateBookingForm.waiting_for_comment, F.text, ~F.text.startswith('/'))
async def process_manual_booking_comment(message: types.Message, state: FSMContext):
    if message.text == ADMIN_SKIP_TEXT:
        comment = None
    else:
        comment, error_message = sanitize_comment(message.text)
        if error_message:
            await message.reply(error_message)
            return
    await state.update_data(comment=comment)
    data = await state.get_data()
    try:
        chosen_date = date.fromisoformat(data['chosen_date'])
    except (KeyError, ValueError):
        await finish_admin_action(
            message,
            state,
            'Данные ручной записи устарели. Начните создание записи заново.',
            section_callback='admin_menu_bookings',
            section_text='К записям',
        )
        return
    summary = (
        'Проверьте ручную запись:\n'
        f'Услуга: {data["service_name"]} ({data["service_duration"]} мин)\n'
        f'Мастер: {data["master_name"]}\n'
        f'Дата: {chosen_date:%d.%m.%Y}\n'
        f'Время: {data["slot_time"]}\n'
        f'Клиент: {data["client_name"]}\n'
        f'Телефон: {data["client_phone"]}'
    )
    if comment:
        summary += f'\nКомментарий: {comment}'
    await message.answer(summary, reply_markup=ReplyKeyboardRemove())
    await message.answer('Создать запись?', reply_markup=create_booking_confirm_kb())
    await state.set_state(AdminCreateBookingForm.waiting_for_confirmation)


@admin_router.callback_query(
    AdminCreateBookingForm.waiting_for_confirmation,
    F.data == 'admin_create_booking_confirm',
)
async def confirm_manual_booking(callback: types.CallbackQuery, state: FSMContext):
    async with callback_action_lock(callback, 'admin_confirm_manual_booking'):
        if not await is_expected_state(state, AdminCreateBookingForm.waiting_for_confirmation):
            await answer_repeated_admin_action(callback)
            return
        data = await state.get_data()
        try:
            chosen_date = date.fromisoformat(data['chosen_date'])
            slot_time = parse_slot_time(data.get('slot_time'))
            if slot_time is None:
                raise ValueError
            date_time = datetime.combine(chosen_date, slot_time)
            client_name = data['client_name']
            client_phone = data['client_phone']
            master_id = data['master_id']
            service_id = data['service_id']
        except (KeyError, ValueError):
            await state.clear()
            await callback.message.edit_text(
                'Данные ручной записи устарели. Начните создание записи заново.',
                reply_markup=admin_after_action_kb('admin_menu_bookings', 'К записям'),
            )
            await callback.answer()
            return
        await callback.message.edit_text('Создаю ручную запись...')
        try:
            async with async_session_maker() as session:
                user = await get_or_create_manual_user(
                    session,
                    full_name=client_name,
                    phone=client_phone,
                )
                appointment = await create_appointment(
                    session,
                    user.id,
                    master_id,
                    service_id,
                    date_time,
                    client_name=client_name,
                    client_phone=client_phone,
                    comment=data.get('comment'),
                )
        except ValueError as error:
            await callback.message.edit_text(
                f'Ошибка: {error}',
                reply_markup=admin_after_action_kb('admin_menu_bookings', 'К записям'),
            )
            await state.clear()
            await callback.answer()
            return

        await state.clear()
        await callback.message.edit_text(
            f'Ручная запись #{appointment.id} создана на {appointment.date_time:%d.%m.%Y %H:%M}.',
            reply_markup=admin_after_action_kb('admin_menu_bookings', 'К записям'),
        )
        await callback.answer()


@admin_router.message(Command('manage_bookings'))
async def cmd_manage_bookings(message: types.Message, state: FSMContext):
    await state.clear()
    async with async_session_maker() as session:
        appointments = await get_future_appointments(session)
    if not appointments:
        await send_admin_result(
            message,
            'Будущих активных записей нет.',
            section_callback='admin_menu_bookings',
            section_text='К записям',
        )
        return
    await message.answer('Выберите запись:', reply_markup=booking_list_kb(appointments))
    await state.set_state(AdminBookingManageForm.waiting_for_appointment)


@admin_router.callback_query(
    AdminBookingManageForm.waiting_for_appointment,
    F.data.startswith('admin_booking_pick_'),
)
async def choose_booking(callback: types.CallbackQuery, state: FSMContext):
    appointment_id = parse_callback_int(callback.data, 'admin_booking_pick_')
    if appointment_id is None:
        await answer_invalid_admin_callback(callback)
        return
    async with async_session_maker() as session:
        appointment = await get_appointment_by_id(session, appointment_id)
    if not appointment or appointment.status != 'active':
        await callback.answer('Запись не найдена или уже не активна.', show_alert=True)
        return
    await state.update_data(
        appointment_id=appointment.id,
        master_id=appointment.master_id,
        service_id=appointment.service_id,
    )
    await callback.message.edit_text(format_appointment_summary(appointment), reply_markup=booking_action_kb())
    await state.set_state(AdminBookingManageForm.waiting_for_action)
    await callback.answer()


@admin_router.callback_query(
    AdminBookingManageForm.waiting_for_action,
    F.data.startswith('admin_booking_action_'),
)
async def choose_booking_action(callback: types.CallbackQuery, state: FSMContext):
    async with callback_action_lock(callback, 'admin_choose_booking_action'):
        if not await is_expected_state(state, AdminBookingManageForm.waiting_for_action):
            await answer_repeated_admin_action(callback)
            return
        action = parse_callback_action(
            callback.data,
            'admin_booking_action_',
            {'cancel', 'reschedule'},
        )
        if action is None:
            await answer_invalid_admin_callback(callback)
            return
        if action == 'cancel':
            await callback.message.edit_text('Введите причину отмены или нажмите «Пропустить»:')
            await callback.message.answer(
                'Причина будет отправлена клиенту.',
                reply_markup=admin_cancel_kb(with_skip=True),
            )
            await state.set_state(AdminBookingManageForm.waiting_for_cancel_reason)
        elif action == 'reschedule':
            await callback.message.edit_text('Выберите новую дату:', reply_markup=booking_date_kb())
            await state.set_state(AdminBookingManageForm.waiting_for_reschedule_date)
        await callback.answer()


@admin_router.message(AdminBookingManageForm.waiting_for_cancel_reason, F.text, ~F.text.startswith('/'))
async def process_booking_cancel_reason(message: types.Message, state: FSMContext, bot: Bot):
    reason = None if message.text == ADMIN_SKIP_TEXT else message.text.strip()
    data = await state.get_data()
    try:
        async with async_session_maker() as session:
            appointment = await cancel_appointment(
                session,
                data['appointment_id'],
                admin_id=message.from_user.id,
                reason=reason,
            )
    except ValueError as error:
        await message.reply(f'Ошибка: {error}')
        return

    await notify_client_booking_cancelled(bot, appointment, reason)
    await finish_admin_action(
        message,
        state,
        f'Запись #{appointment.id} отменена.',
        section_callback='admin_menu_bookings',
        section_text='К записям',
    )


@admin_router.callback_query(
    AdminBookingManageForm.waiting_for_reschedule_date,
    F.data.startswith('admin_booking_date_'),
)
async def choose_booking_reschedule_date(callback: types.CallbackQuery, state: FSMContext):
    chosen_date = parse_callback_date(callback.data, 'admin_booking_date_')
    if chosen_date is None:
        await answer_invalid_admin_callback(callback)
        return
    data = await state.get_data()
    appointment_id = data.get('appointment_id')
    if appointment_id is None:
        await state.clear()
        await callback.message.edit_text(
            'Данные управления записью устарели. Откройте список записей заново.',
            reply_markup=admin_after_action_kb('admin_menu_bookings', 'К записям'),
        )
        await callback.answer()
        return
    async with async_session_maker() as session:
        appointment = await get_appointment_by_id(session, appointment_id)
        if not appointment or appointment.status != 'active':
            await callback.answer('Запись не найдена или уже не активна.', show_alert=True)
            return
        free_slots = await get_free_slots(session, appointment.master_id, appointment.service_id, chosen_date)
    if not free_slots:
        await callback.message.edit_text(
            'На эту дату нет свободного времени. Выберите другую дату:',
            reply_markup=booking_date_kb(),
        )
        await callback.answer()
        return
    await state.update_data(chosen_date=chosen_date.isoformat())
    await callback.message.edit_text('Выберите новое время:', reply_markup=booking_slots_kb(free_slots))
    await state.set_state(AdminBookingManageForm.waiting_for_reschedule_time)
    await callback.answer()


@admin_router.callback_query(
    AdminBookingManageForm.waiting_for_reschedule_time,
    F.data.startswith('admin_booking_slot_'),
)
async def choose_booking_reschedule_time(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    async with callback_action_lock(callback, 'admin_reschedule_booking'):
        if not await is_expected_state(state, AdminBookingManageForm.waiting_for_reschedule_time):
            await answer_repeated_admin_action(callback)
            return
        slot_time = parse_callback_slot(callback.data, 'admin_booking_slot_')
        if slot_time is None:
            await answer_invalid_admin_callback(callback)
            return
        data = await state.get_data()
        try:
            chosen_date = date.fromisoformat(data['chosen_date'])
            appointment_id = data['appointment_id']
        except (KeyError, ValueError):
            await state.clear()
            await callback.message.edit_text(
                'Данные переноса записи устарели. Откройте список записей заново.',
                reply_markup=admin_after_action_kb('admin_menu_bookings', 'К записям'),
            )
            await callback.answer()
            return
        new_date_time = datetime.combine(chosen_date, slot_time)
        try:
            async with async_session_maker() as session:
                appointment = await reschedule_appointment(session, appointment_id, new_date_time)
        except ValueError as error:
            await callback.answer(str(error), show_alert=True)
            return

        await notify_client_booking_rescheduled(bot, appointment)
        await state.clear()
        await callback.message.edit_text(
            f'Запись #{appointment.id} перенесена на {appointment.date_time:%d.%m.%Y %H:%M}.',
            reply_markup=admin_after_action_kb('admin_menu_bookings', 'К записям'),
        )
        await callback.answer()


@admin_router.message(Command('add_closed_date'))
async def cmd_add_closed_date(message: types.Message, state: FSMContext):
    parts = message.text.split(maxsplit=2)
    if len(parts) >= 2:
        try:
            closed_date = parse_admin_date(parts[1])
            reason = parts[2].strip() if len(parts) == 3 else None
            async with async_session_maker() as session:
                await add_closed_date(session, closed_date, reason)
        except ValueError as error:
            await message.reply(f'Ошибка: {error}')
            return
        await send_admin_result(
            message,
            f'Дата {closed_date.strftime("%d.%m.%Y")} отмечена как выходная.',
            section_callback='admin_menu_closed_dates',
            section_text='К выходным',
        )
        return

    await state.clear()
    await message.answer('Введите дату выходного дня: ДД.ММ.ГГГГ или YYYY-MM-DD', reply_markup=admin_cancel_kb())
    await state.set_state(AdminClosedDateForm.waiting_for_date)


@admin_router.message(AdminClosedDateForm.waiting_for_date, F.text, ~F.text.startswith('/'))
async def process_closed_date(message: types.Message, state: FSMContext):
    try:
        closed_date = parse_admin_date(message.text.strip())
    except ValueError:
        await message.reply('Не понял дату. Введите в формате 31.12.2026 или 2026-12-31.')
        return
    await state.update_data(closed_date=closed_date.isoformat())
    await message.answer(
        'Введите причину выходного дня или нажмите «Пропустить»:',
        reply_markup=admin_cancel_kb(with_skip=True),
    )
    await state.set_state(AdminClosedDateForm.waiting_for_reason)


@admin_router.message(AdminClosedDateForm.waiting_for_reason, F.text, ~F.text.startswith('/'))
async def process_closed_date_reason(message: types.Message, state: FSMContext):
    reason = None if message.text == ADMIN_SKIP_TEXT else message.text.strip()
    data = await state.get_data()
    try:
        closed_date = date.fromisoformat(data['closed_date'])
    except (KeyError, ValueError):
        await finish_admin_action(
            message,
            state,
            'Данные выходной даты устарели. Начните добавление заново.',
            section_callback='admin_menu_closed_dates',
            section_text='К выходным',
        )
        return
    try:
        async with async_session_maker() as session:
            await add_closed_date(session, closed_date, reason)
    except ValueError as error:
        await message.reply(f'Ошибка: {error}')
        return
    await finish_admin_action(
        message,
        state,
        f'Дата {closed_date.strftime("%d.%m.%Y")} отмечена как выходная.',
        section_callback='admin_menu_closed_dates',
        section_text='К выходным',
    )


@admin_router.message(Command('remove_closed_date'))
async def cmd_remove_closed_date(message: types.Message, state: FSMContext):
    parts = message.text.split(maxsplit=1)
    if len(parts) == 2:
        try:
            closed_date = parse_admin_date(parts[1])
            async with async_session_maker() as session:
                removed = await remove_closed_date(session, closed_date)
        except ValueError as error:
            await message.reply(f'Ошибка: {error}')
            return
        if not removed:
            await send_admin_result(
                message,
                'Эта дата не была отмечена как выходная.',
                section_callback='admin_menu_closed_dates',
                section_text='К выходным',
            )
            return
        await send_admin_result(
            message,
            f'Дата {closed_date.strftime("%d.%m.%Y")} снова доступна для записи.',
            section_callback='admin_menu_closed_dates',
            section_text='К выходным',
        )
        return

    await state.clear()
    async with async_session_maker() as session:
        closed_dates = await get_closed_dates(session)
    if not closed_dates:
        await send_admin_result(
            message,
            'Ручных выходных дней нет.',
            section_callback='admin_menu_closed_dates',
            section_text='К выходным',
        )
        return
    await message.answer('Выберите дату, которую нужно открыть:', reply_markup=closed_dates_kb(closed_dates))


@admin_router.callback_query(F.data.startswith('admin_closed_remove_'))
async def remove_closed_date_callback(callback: types.CallbackQuery, state: FSMContext):
    closed_date = parse_callback_date(callback.data, 'admin_closed_remove_')
    if closed_date is None:
        await answer_invalid_admin_callback(callback)
        return
    async with async_session_maker() as session:
        removed = await remove_closed_date(session, closed_date)
    await state.clear()
    if removed:
        await callback.message.edit_text(
            f'Дата {closed_date.strftime("%d.%m.%Y")} снова доступна для записи.',
            reply_markup=admin_after_action_kb('admin_menu_closed_dates', 'К выходным'),
        )
    else:
        await callback.message.edit_text(
            'Эта дата уже не была отмечена как выходная.',
            reply_markup=admin_after_action_kb('admin_menu_closed_dates', 'К выходным'),
        )
    await callback.answer()


@admin_router.message(Command('list_closed_dates'))
async def cmd_list_closed_dates(message: types.Message):
    async with async_session_maker() as session:
        closed_dates = await get_closed_dates(session)
    if not closed_dates:
        await send_admin_result(
            message,
            'Ручных выходных дней нет.',
            section_callback='admin_menu_closed_dates',
            section_text='К выходным',
        )
        return
    lines = ['Ручные выходные дни:']
    for item in closed_dates:
        line = f'• {item.date.strftime("%d.%m.%Y")}'
        if item.reason:
            line += f' — {item.reason}'
        lines.append(line)
    await send_admin_result(
        message,
        '\n'.join(lines),
        section_callback='admin_menu_closed_dates',
        section_text='К выходным',
    )


@admin_router.callback_query(F.data.startswith('admin_'))
async def unmatched_admin_callback(callback: types.CallbackQuery, state: FSMContext):
    await answer_unmatched_admin_callback(callback, state)
