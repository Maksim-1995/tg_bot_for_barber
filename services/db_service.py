from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timedelta

from models import Service, Master, Schedule, User, Appointment



# ---------- Услуги ----------
async def add_service(session: AsyncSession, name: str, duration: int):
    new_service = Service(name=name, duration=duration)
    session.add(new_service)
    await session.commit()
    return new_service

async def get_services(session: AsyncSession):
    result = await session.execute(select(Service))
    return result.scalars().all()

# ---------- Мастера ----------
async def add_master(session: AsyncSession, full_name: str, description: str, service_ids: list[int]):
    # Получаем услуги по ID
    services = await session.execute(select(Service).where(Service.id.in_(service_ids)))
    services = services.scalars().all()
    new_master = Master(full_name=full_name, description=description)
    new_master.services = services
    session.add(new_master)
    await session.commit()
    return new_master

async def get_masters_by_service(session: AsyncSession, service_id: int):
    """
    Возвращает мастеров, которые оказывают указанную услугу.
    
    Если связей нет – всех мастеров.
    """
    service = await session.get(Service, service_id)
    if not service:
        return []
    masters = await session.execute(
        select(Master).where(Master.services.contains(service))
    )
    result = masters.scalars().all()
    if not result:
        # Если связь не задана, вернуть всех мастеров.
        all_masters = await session.execute(select(Master))
        return all_masters.scalars().all()
    return result

# ---------- Пользователи ----------
async def get_or_create_user(session: AsyncSession, telegram_id: int, full_name: str, phone: str = None):
    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()
    if not user:
        user = User(telegram_id=telegram_id, full_name=full_name, phone_number=phone)
        session.add(user)
        await session.commit()
    return user

# ---------- Записи ----------
async def create_appointment(session: AsyncSession, user_id: int, master_id: int,
                             service_id: int, date_time: datetime, comment: str = None):
    service = await session.get(Service, service_id)
    if not service:
        raise ValueError('Услуга не найдена')
    end_time = date_time + timedelta(minutes=service.duration)
    # Проверка на двойную запись (конкурентная проверка).
    # Ищем пересекающиеся записи у этого мастера.
    collision = await session.execute(
        select(Appointment).where(
            Appointment.master_id == master_id,
            Appointment.date_time < end_time,
            Appointment.end_time > date_time
        )
    )
    if collision.scalars().first():
        raise ValueError('Это время уже занято')
    appointment = Appointment(
        user_id=user_id,
        master_id=master_id,
        service_id=service_id,
        date_time=date_time,
        end_time=end_time,
        comment=comment
    )
    session.add(appointment)
    await session.commit()
    return appointment

async def set_master_schedule(
    session: AsyncSession,
    master_id: int,
    day_of_week: int,
    start_time: datetime,
    end_time,
    lunch_start=None,
    lunch_end=None
):
    """Создаёт или обновляет запись расписания для мастера на указанный день недели."""
    # Ищем существующую запись.
    result = await session.execute(
        select(Schedule).where(
            Schedule.master_id == master_id,
            Schedule.day_of_week == day_of_week
        )
    )
    schedule = result.scalar_one_or_none()
    if schedule:
        schedule.start_time = start_time
        schedule.end_time = end_time
        schedule.is_working = 1
        schedule.lunch_start = lunch_start
        schedule.lunch_end = lunch_end
    else:
        schedule = Schedule(
            master_id=master_id,
            day_of_week=day_of_week,
            start_time=start_time,
            end_time=end_time,
            lunch_start=lunch_start,
            lunch_end=lunch_end
        )
        session.add(schedule)
    await session.commit()

async def get_future_appointments(session: AsyncSession):
    """Возвращает все записи, начиная с текущего момента, отсортированные по дате."""
    now = datetime.now()
    result = await session.execute(
        select(Appointment)
        .where(Appointment.date_time >= now)
        .order_by(Appointment.date_time)
    )
    return result.scalars().all()

async def get_appointment_by_id(session: AsyncSession, appointment_id: int):
    """Возвращает запись по ID."""
    return await session.get(Appointment, appointment_id)
