"""Вспомогательные функции работы с датой и временем."""

from datetime import datetime
from zoneinfo import ZoneInfo


MOSCOW_TZ = ZoneInfo('Europe/Moscow')


def now_moscow():
    """Возвращает текущее время в часовом поясе Москвы."""
    return datetime.now(MOSCOW_TZ)
