import asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload
from datetime import date, datetime, time, timedelta

from models import Appointment, ClosedDate, Master, Schedule, Service, User, master_service
from utils.constants import DEFAULT_SLOT_INTERVAL, SLOT_STEP


_appointment_creation_lock = asyncio.Lock()
APPOINTMENT_STATUS_ACTIVE = 'active'
APPOINTMENT_STATUS_CANCELLED = 'cancelled'



# ---------- Услуги ----------
async def add_service(session: AsyncSession, name: str, duration: int):
    name = name.strip()
    if not name:
        raise ValueError('Название услуги не может быть пустым')
    if duration <= 0:
        raise ValueError('Длительность услуги должна быть больше 0 минут')
    existing = await session.execute(select(Service).where(Service.name == name))
    if existing.scalar_one_or_none():
        raise ValueError('Услуга с таким названием уже существует')
    new_service = Service(name=name, duration=duration)
    session.add(new_service)
    await session.commit()
    return new_service


async def get_services(session: AsyncSession, *, active_only: bool = True):
    query = select(Service).order_by(Service.id)
    if active_only:
        query = query.where(Service.is_active == 1)
    result = await session.execute(query)
    return result.scalars().all()


async def get_service(session: AsyncSession, service_id: int):
    return await session.get(Service, service_id)


async def update_service(
    session: AsyncSession,
    service_id: int,
    *,
    name: str | None = None,
    duration: int | None = None,
):
    service = await session.get(Service, service_id)
    if not service:
        raise ValueError('Услуга не найдена')
    if name is not None:
        name = name.strip()
        if not name:
            raise ValueError('Название услуги не может быть пустым')
        existing = await session.execute(
            select(Service).where(Service.name == name, Service.id != service_id)
        )
        if existing.scalar_one_or_none():
            raise ValueError('Услуга с таким названием уже существует')
        service.name = name
    if duration is not None:
        if duration <= 0:
            raise ValueError('Длительность услуги должна быть больше 0 минут')
        service.duration = duration
    await session.commit()
    return service


async def set_service_active(session: AsyncSession, service_id: int, is_active: bool):
    service = await session.get(Service, service_id)
    if not service:
        raise ValueError('Услуга не найдена')
    service.is_active = 1 if is_active else 0
    await session.commit()
    return service

# ---------- Мастера ----------
async def add_master(session: AsyncSession, full_name: str, description: str, service_ids: list[int]):
    full_name = full_name.strip()
    description = description.strip()
    if not full_name:
        raise ValueError('Имя мастера не может быть пустым')
    if not service_ids:
        raise ValueError('Укажите хотя бы одну услугу')
    # Получаем услуги по ID
    services = await session.execute(
        select(Service).where(Service.id.in_(service_ids), Service.is_active == 1)
    )
    services = services.scalars().all()
    if len(services) != len(set(service_ids)):
        raise ValueError('Одна или несколько услуг не найдены или отключены')
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
    if not service or service.is_active != 1:
        return []
    masters = await session.execute(
        select(Master).where(
            Master.services.contains(service),
            Master.is_active == 1,
        )
    )
    result = masters.scalars().all()
    if not result:
        # Если связь не задана, вернуть всех мастеров.
        all_masters = await session.execute(select(Master).where(Master.is_active == 1))
        return all_masters.scalars().all()
    return result


async def get_masters(session: AsyncSession, *, active_only: bool = True):
    query = (
        select(Master)
        .options(selectinload(Master.services))
        .order_by(Master.id)
    )
    if active_only:
        query = query.where(Master.is_active == 1)
    result = await session.execute(
        query
    )
    return result.scalars().all()


async def get_master(session: AsyncSession, master_id: int):
    result = await session.execute(
        select(Master)
        .options(selectinload(Master.services))
        .where(Master.id == master_id)
    )
    return result.scalar_one_or_none()


async def update_master(
    session: AsyncSession,
    master_id: int,
    *,
    full_name: str | None = None,
    description: str | None = None,
):
    master = await session.get(Master, master_id)
    if not master:
        raise ValueError('Мастер не найден')
    if full_name is not None:
        full_name = full_name.strip()
        if not full_name:
            raise ValueError('Имя мастера не может быть пустым')
        master.full_name = full_name
    if description is not None:
        master.description = description.strip()
    await session.commit()
    return master


async def set_master_services(session: AsyncSession, master_id: int, service_ids: list[int]):
    master = await session.get(Master, master_id)
    if not master:
        raise ValueError('Мастер не найден')
    if not service_ids:
        raise ValueError('Укажите хотя бы одну услугу')
    services = await session.execute(
        select(Service).where(Service.id.in_(service_ids), Service.is_active == 1)
    )
    services = services.scalars().all()
    if len(services) != len(set(service_ids)):
        raise ValueError('Одна или несколько услуг не найдены или отключены')
    master.services = services
    await session.commit()
    return master


async def set_master_active(session: AsyncSession, master_id: int, is_active: bool):
    master = await session.get(Master, master_id)
    if not master:
        raise ValueError('Мастер не найден')
    master.is_active = 1 if is_active else 0
    await session.commit()
    return master

# ---------- Пользователи ----------
async def get_or_create_user(session: AsyncSession, telegram_id: int, full_name: str, phone: str = None):
    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()
    if not user:
        user = User(telegram_id=telegram_id, full_name=full_name, phone_number=phone)
        session.add(user)
        await session.commit()
    else:
        user.full_name = full_name
        user.phone_number = phone
        await session.commit()
    return user


async def get_or_create_manual_user(session: AsyncSession, full_name: str, phone: str):
    """Создаёт технического пользователя для записи клиента без Telegram."""
    result = await session.execute(
        select(User).where(
            User.telegram_id < 0,
            User.phone_number == phone,
        )
    )
    user = result.scalar_one_or_none()
    if user:
        user.full_name = full_name
        await session.commit()
        return user

    min_telegram_id_result = await session.execute(
        select(func.min(User.telegram_id)).where(User.telegram_id < 0)
    )
    min_telegram_id = min_telegram_id_result.scalar_one_or_none()
    telegram_id = (min_telegram_id or 0) - 1
    user = User(telegram_id=telegram_id, full_name=full_name, phone_number=phone)
    session.add(user)
    await session.commit()
    return user

# ---------- Записи ----------
async def create_appointment(
    session: AsyncSession,
    user_id: int,
    master_id: int,
    service_id: int,
    date_time: datetime,
    client_name: str,
    client_phone: str,
    comment: str = None,
):
    async with _appointment_creation_lock:
        try:
            await session.execute(text('BEGIN IMMEDIATE'))

            service = await session.get(Service, service_id)
            if not service or service.is_active != 1:
                raise ValueError('Услуга не найдена')

            master = await session.get(Master, master_id)
            if not master or master.is_active != 1:
                raise ValueError('Мастер не найден')

            end_time = date_time + timedelta(minutes=service.duration)
            await ensure_slot_available(session, master_id, service_id, date_time, end_time)

            appointment = Appointment(
                user_id=user_id,
                master_id=master_id,
                service_id=service_id,
                client_name=client_name,
                client_phone=client_phone,
                date_time=date_time,
                end_time=end_time,
                status=APPOINTMENT_STATUS_ACTIVE,
                comment=comment
            )
            session.add(appointment)
            await session.commit()
            return appointment
        except IntegrityError as error:
            await session.rollback()
            raise ValueError('Это время уже занято') from error
        except Exception:
            await session.rollback()
            raise


async def ensure_slot_available(
    session: AsyncSession,
    master_id: int,
    service_id: int,
    date_time: datetime,
    end_time: datetime | None = None,
    exclude_appointment_id: int | None = None,
) -> None:
    """Проверяет, что слот всё ещё входит в расписание и не занят."""
    service = await session.get(Service, service_id)
    if not service or service.is_active != 1:
        raise ValueError('Услуга не найдена')

    master = await session.get(Master, master_id)
    if not master or master.is_active != 1:
        raise ValueError('Мастер не найден')

    assigned_masters_result = await session.execute(
        select(master_service.c.master_id).where(master_service.c.service_id == service_id)
    )
    assigned_master_ids = set(assigned_masters_result.scalars().all())
    if assigned_master_ids and master_id not in assigned_master_ids:
        raise ValueError('Мастер не выполняет выбранную услугу')

    if end_time is None:
        end_time = date_time + timedelta(minutes=service.duration)

    closed_date_result = await session.execute(
        select(ClosedDate).where(ClosedDate.date == date_time.date())
    )
    if closed_date_result.scalar_one_or_none():
        raise ValueError('На выбранную дату салон закрыт')

    schedule_result = await session.execute(
        select(Schedule).where(
            Schedule.master_id == master_id,
            Schedule.day_of_week == date_time.weekday(),
            Schedule.is_working == 1,
        )
    )
    schedule = schedule_result.scalar_one_or_none()
    if not schedule:
        raise ValueError('Мастер не работает в выбранный день')

    work_start = datetime.combine(date_time.date(), schedule.start_time)
    work_end = datetime.combine(date_time.date(), schedule.end_time)
    if date_time < work_start or end_time > work_end:
        raise ValueError('Выбранное время вне рабочего графика мастера')

    minutes_from_start = int((date_time - work_start).total_seconds() // 60)
    required_interval = DEFAULT_SLOT_INTERVAL if service.duration <= DEFAULT_SLOT_INTERVAL else SLOT_STEP
    if minutes_from_start < 0 or minutes_from_start % required_interval != 0:
        raise ValueError('Выбранное время не соответствует сетке записи')

    if schedule.lunch_start and schedule.lunch_end:
        lunch_start = datetime.combine(date_time.date(), schedule.lunch_start)
        lunch_end = datetime.combine(date_time.date(), schedule.lunch_end)
        if date_time < lunch_end and end_time > lunch_start:
            raise ValueError('Выбранное время пересекается с обедом мастера')

    collision_query = select(Appointment).where(
        Appointment.master_id == master_id,
        Appointment.status == APPOINTMENT_STATUS_ACTIVE,
        Appointment.date_time < end_time,
        Appointment.end_time > date_time
    )
    if exclude_appointment_id is not None:
        collision_query = collision_query.where(Appointment.id != exclude_appointment_id)
    collision = await session.execute(collision_query)
    if collision.scalars().first():
        raise ValueError('Это время уже занято')

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
    if not (0 <= day_of_week <= 6):
        raise ValueError('День недели должен быть от 0 до 6')
    if start_time >= end_time:
        raise ValueError('Время начала должно быть раньше времени окончания')
    if (lunch_start is None) != (lunch_end is None):
        raise ValueError('Укажите и начало, и конец обеда')
    if lunch_start and lunch_end:
        if lunch_start >= lunch_end:
            raise ValueError('Начало обеда должно быть раньше конца обеда')
        if lunch_start < start_time or lunch_end > end_time:
            raise ValueError('Обед должен быть внутри рабочего дня')
    master = await session.get(Master, master_id)
    if not master:
        raise ValueError('Мастер не найден')
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


async def set_master_day_off(session: AsyncSession, master_id: int, day_of_week: int) -> None:
    """Отмечает день недели как нерабочий для мастера."""
    if not (0 <= day_of_week <= 6):
        raise ValueError('День недели должен быть от 0 до 6')
    master = await session.get(Master, master_id)
    if not master:
        raise ValueError('Мастер не найден')

    result = await session.execute(
        select(Schedule).where(
            Schedule.master_id == master_id,
            Schedule.day_of_week == day_of_week
        )
    )
    schedule = result.scalar_one_or_none()
    if schedule:
        schedule.is_working = 0
    else:
        schedule = Schedule(
            master_id=master_id,
            day_of_week=day_of_week,
            start_time=time(0, 0),
            end_time=time(0, 0),
            is_working=0,
        )
        session.add(schedule)
    await session.commit()

async def get_future_appointments(session: AsyncSession):
    """Возвращает все записи, начиная с текущего момента, отсортированные по дате."""
    now = datetime.now()
    result = await session.execute(
        select(Appointment)
        .options(
            selectinload(Appointment.service),
            selectinload(Appointment.master),
            selectinload(Appointment.user),
        )
        .where(Appointment.date_time >= now)
        .where(Appointment.status == APPOINTMENT_STATUS_ACTIVE)
        .order_by(Appointment.date_time)
    )
    return result.scalars().all()

async def get_appointment_by_id(session: AsyncSession, appointment_id: int):
    """Возвращает запись по ID."""
    result = await session.execute(
        select(Appointment)
        .options(
            selectinload(Appointment.service),
            selectinload(Appointment.master),
            selectinload(Appointment.user),
        )
        .where(Appointment.id == appointment_id)
    )
    return result.scalar_one_or_none()


async def cancel_appointment(
    session: AsyncSession,
    appointment_id: int,
    admin_id: int,
    reason: str | None = None,
):
    appointment = await get_appointment_by_id(session, appointment_id)
    if not appointment:
        raise ValueError('Запись не найдена')
    if appointment.status != APPOINTMENT_STATUS_ACTIVE:
        raise ValueError('Запись уже не активна')
    appointment.status = APPOINTMENT_STATUS_CANCELLED
    appointment.cancelled_at = datetime.now()
    appointment.cancelled_by_admin_id = admin_id
    appointment.cancel_reason = reason.strip() if reason else None
    await session.commit()
    return appointment


async def reschedule_appointment(
    session: AsyncSession,
    appointment_id: int,
    new_date_time: datetime,
):
    async with _appointment_creation_lock:
        try:
            await session.execute(text('BEGIN IMMEDIATE'))
            appointment = await get_appointment_by_id(session, appointment_id)
            if not appointment:
                raise ValueError('Запись не найдена')
            if appointment.status != APPOINTMENT_STATUS_ACTIVE:
                raise ValueError('Запись уже не активна')

            service = await session.get(Service, appointment.service_id)
            if not service:
                raise ValueError('Услуга не найдена')
            new_end_time = new_date_time + timedelta(minutes=service.duration)
            await ensure_slot_available(
                session,
                appointment.master_id,
                appointment.service_id,
                new_date_time,
                new_end_time,
                exclude_appointment_id=appointment.id,
            )
            appointment.date_time = new_date_time
            appointment.end_time = new_end_time
            await session.commit()
            return appointment
        except Exception:
            await session.rollback()
            raise


async def add_closed_date(session: AsyncSession, closed_date: date, reason: str | None = None):
    """Добавляет ручной выходной день."""
    existing = await session.execute(select(ClosedDate).where(ClosedDate.date == closed_date))
    if existing.scalar_one_or_none():
        raise ValueError('Эта дата уже отмечена как выходная')
    item = ClosedDate(date=closed_date, reason=reason)
    session.add(item)
    await session.commit()
    return item


async def remove_closed_date(session: AsyncSession, closed_date: date) -> bool:
    """Удаляет ручной выходной день."""
    result = await session.execute(select(ClosedDate).where(ClosedDate.date == closed_date))
    item = result.scalar_one_or_none()
    if not item:
        return False
    await session.delete(item)
    await session.commit()
    return True


async def get_closed_dates(session: AsyncSession):
    """Возвращает список ручных выходных дней."""
    result = await session.execute(select(ClosedDate).order_by(ClosedDate.date))
    return result.scalars().all()
