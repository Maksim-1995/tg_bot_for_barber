"""Логика работы с датами и временными слотами."""

from datetime import datetime, timedelta, time, date
from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from aiogram.utils.keyboard import InlineKeyboardBuilder

from models import Schedule, Appointment, Service
from utils.constants import DAYS_AHEAD, DEFAULT_SLOT_INTERVAL, SLOT_STEP


async def generate_date_keyboard() -> InlineKeyboardBuilder:
    """Создаёт клавиатуру с ближайшими датами (кнопки ДД.ММ)."""
    builder = InlineKeyboardBuilder()
    today = date.today()
    for day_offset in range(DAYS_AHEAD):
        day = today + timedelta(days=day_offset)
        day_str = day.strftime('%d.%m')
        builder.button(text=day_str, callback_data=f'date_{day.isoformat()}')
    builder.button(text='◀️ Назад', callback_data='cancel')
    builder.adjust(4)  # по 4 кнопки в ряд
    return builder

async def get_free_slots(
    session: AsyncSession,
    master_id: int,
    service_id: int,
    selected_date: date,
) -> List[str]:
    """
    Возвращает список свободных слотов.
    
    (в формате 'ЧЧ:ММ') для выбранного мастера,
    услуги и даты. Если слотов нет — пустой список.
    """
    # Получаем расписание мастера на этот день недели
    day_of_week = selected_date.weekday()  # 0=ПН
    schedule_result = await session.execute(
        select(Schedule).where(
            Schedule.master_id == master_id,
            Schedule.day_of_week == day_of_week,
            Schedule.is_working == 1
        )
    )
    schedule = schedule_result.scalar_one_or_none()
    if not schedule:
        return []  # нерабочий день
    # Длительность услуги
    service_result = await session.get(Service, service_id)
    if not service_result:
        return []
    service_duration = service_result.duration
    # Интервал между слотами (пока берём из константы, позже можно вынести в настройки)
    slot_interval = DEFAULT_SLOT_INTERVAL
    # Границы рабочего дня
    start_time = schedule.start_time
    end_time = schedule.end_time
    lunch_start = schedule.lunch_start
    lunch_end = schedule.lunch_end
    # Формируем возможные слоты: начинаем с start_time, шаг SLOT_STEP минут
    slots = []
    current_time = datetime.combine(selected_date, start_time)
    end_datetime = datetime.combine(selected_date, end_time)
    while current_time + timedelta(minutes=service_duration) <= end_datetime:
        slot_start = current_time.time()
        slot_end = (current_time + timedelta(minutes=service_duration)).time()
        # Пропускаем слоты, попадающие на обед
        if lunch_start and lunch_end:
            lunch_start_dt = datetime.combine(selected_date, lunch_start)
            lunch_end_dt = datetime.combine(selected_date, lunch_end)
            slot_start_dt = datetime.combine(selected_date, slot_start)
            slot_end_dt = datetime.combine(selected_date, slot_end)
            if not (slot_end_dt <= lunch_start_dt or slot_start_dt >= lunch_end_dt):
                # Слот пересекается с обедом — пропускаем
                current_time += timedelta(minutes=SLOT_STEP)
                continue
        slots.append(slot_start.strftime('%H:%M'))
        current_time += timedelta(minutes=SLOT_STEP)
    # Убираем уже занятые слоты (по записям в БД)
    appointments_result = await session.execute(
        select(Appointment).where(
            Appointment.master_id == master_id,
            Appointment.date_time >= datetime.combine(selected_date, start_time),
            Appointment.end_time <= datetime.combine(selected_date, end_time)
        )
    )
    busy_periods = []
    for appointment in appointments_result.scalars().all():
        busy_periods.append((appointment.date_time.time(), appointment.end_time.time()))
    # Фильтруем свободные слоты, которые не пересекаются с занятыми
    free_slots = []
    for slot_str in slots:
        slot_hour, slot_minute = map(int, slot_str.split(':'))
        slot_start = time(slot_hour, slot_minute)
        slot_end = (
            datetime.combine(selected_date, slot_start) + timedelta(minutes=service_duration)
        ).time()
        is_busy = False
        for busy_start, busy_end in busy_periods:
            if slot_start < busy_end and slot_end > busy_start:
                is_busy = True
                break
        if not is_busy:
            free_slots.append(slot_str)
    # Оставляем слоты, кратные интервалу (например, каждый час — 10:00, 11:00, ...)
    # Но если услуга длится дольше интервала, слоты могут быть реже
    if slot_interval > 0 and service_duration <= slot_interval:
        # Фильтруем по шагу интервала
        step = slot_interval // SLOT_STEP  # сколько шагов между разрешёнными слотами
        free_slots = [slot for i, slot in enumerate(free_slots) if i % step == 0]
    # Если услуга длиннее интервала, этот фильтр не применяем, чтобы не потерять возможные слоты
    return free_slots
