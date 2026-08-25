"""Формирование и отправка уведомлений."""

import logging

from aiogram import Bot

from config import settings
from utils.constants import SALON_ADDRESS


logger = logging.getLogger(__name__)


def format_new_booking_admin_message(
    client_name: str,
    service_name: str,
    master_name: str,
    date_time_str: str,
    phone: str,
    comment: str | None = None,
) -> str:
    """Собирает текст уведомления администратору о новой записи."""
    message = (
        f'🆕 Новая запись:\n'
        f'Клиент: {client_name}\n'
        f'Услуга: {service_name}\n'
        f'Мастер: {master_name}\n'
        f'Дата: {date_time_str}\n'
        f'Телефон: {phone}'
    )
    if comment:
        message += f'\nКомментарий: {comment}'
    return message


def format_client_booking_confirmed_message() -> str:
    """Собирает подтверждение записи для клиента."""
    return f'✅ Вы записаны! Ждём вас по адресу: {SALON_ADDRESS}'


def appointment_service_name(appointment) -> str:
    service = getattr(appointment, 'service', None)
    if service and getattr(service, 'name', None):
        return service.name
    return getattr(appointment, 'service_name', None) or 'услуга'


def appointment_master_name(appointment) -> str:
    master = getattr(appointment, 'master', None)
    if master and getattr(master, 'full_name', None):
        return master.full_name
    return getattr(appointment, 'master_name', None) or 'мастер'


def format_client_booking_cancelled_message(appointment, reason: str | None = None) -> str:
    """Собирает уведомление клиенту об отмене записи администратором."""
    message = (
        f'Ваша запись на {appointment.date_time:%d.%m.%Y %H:%M} '
        f'({appointment_service_name(appointment)}, мастер {appointment_master_name(appointment)}) '
        f'отменена администратором.'
    )
    if reason:
        message += f'\nПричина: {reason}'
    return message


def format_client_booking_rescheduled_message(appointment) -> str:
    """Собирает уведомление клиенту о переносе записи администратором."""
    return (
        f'Ваша запись перенесена на {appointment.date_time:%d.%m.%Y %H:%M}.\n'
        f'Услуга: {appointment_service_name(appointment)}\n'
        f'Мастер: {appointment_master_name(appointment)}'
    )


async def safe_send_message(bot: Bot, chat_id: int, text: str) -> bool:
    """Отправляет сообщение и логирует ошибку без падения сценария."""
    try:
        await bot.send_message(chat_id, text)
    except Exception as error:
        logger.error('Не удалось отправить уведомление в чат %s: %s', chat_id, error)
        return False
    return True


async def notify_admins(bot: Bot, client_name: str, service_name: str,
                        master_name: str, date_time_str: str,
                        phone: str, comment: str = None):
    """Отправляет сообщение о новой записи всем администраторам."""
    message = format_new_booking_admin_message(
        client_name,
        service_name,
        master_name,
        date_time_str,
        phone,
        comment,
    )
    for admin_id in settings.ADMIN_IDS:
        await safe_send_message(bot, admin_id, message)


async def notify_booking_client(bot: Bot, appointment, text: str) -> bool:
    """Отправляет уведомление клиенту по записи."""
    user = getattr(appointment, 'user', None)
    telegram_id = getattr(user, 'telegram_id', None)
    if not telegram_id or telegram_id <= 0:
        return False
    return await safe_send_message(bot, telegram_id, text)


async def notify_client_booking_cancelled(bot: Bot, appointment, reason: str | None = None) -> bool:
    return await notify_booking_client(
        bot,
        appointment,
        format_client_booking_cancelled_message(appointment, reason),
    )


async def notify_client_booking_rescheduled(bot: Bot, appointment) -> bool:
    return await notify_booking_client(
        bot,
        appointment,
        format_client_booking_rescheduled_message(appointment),
    )
