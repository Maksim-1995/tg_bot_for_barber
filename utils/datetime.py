from datetime import datetime
from zoneinfo import ZoneInfo


MOSCOW_TZ = ZoneInfo('Europe/Moscow')


def now_moscow():
    return datetime.now(MOSCOW_TZ)
