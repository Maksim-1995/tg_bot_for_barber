"""Отправка уведомлений администраторам."""

from aiogram import Bot

from config import settings


async def notify_admins(bot: Bot, client_name: str, service_name: str,
                        master_name: str, date_time_str: str,
                        phone: str, comment: str = None):
    """Отправляет сообщение о новой записи всем администраторам."""
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
    for admin_id in settings.ADMIN_IDS:
        try:
            await bot.send_message(admin_id, message)
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(
                'Не удалось отправить уведомление админу %s: %s',
                admin_id,
                e
            )
