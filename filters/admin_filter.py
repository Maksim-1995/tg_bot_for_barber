from aiogram.filters import BaseFilter
from aiogram.types import CallbackQuery, Message

from config import settings


class IsAdmin(BaseFilter):
    """Фильтр для проверки, является ли пользователь администратором."""

    async def __call__(self, event: Message | CallbackQuery) -> bool:
        return event.from_user.id in settings.ADMIN_IDS
