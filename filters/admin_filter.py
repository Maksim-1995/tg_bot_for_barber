from aiogram.filters import BaseFilter
from aiogram.types import Message

from config import settings


class IsAdmin(BaseFilter):
    """Фильтр для проверки, является ли пользователь администратором."""

    async def __call__(self, message: Message) -> bool:
        return message.from_user.id in settings.ADMIN_IDS
