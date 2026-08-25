"""Заполняет SQLite-базу демонстрационным салоном."""

import os
import sys
from datetime import time
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, selectinload

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from models import Base, Master, SalonSetting, Schedule, Service
from services.db_service import (
    DEMO_MASTERS,
    DEMO_SERVICES,
    SALON_ADDRESS_SETTING_KEY,
    SLOT_INTERVAL_SETTING_KEY,
)
from utils.constants import DEFAULT_SALON_ADDRESS, DEFAULT_SLOT_INTERVAL


def get_sync_database_url() -> str:
    load_dotenv(ROOT_DIR / '.env')
    database_url = os.getenv('DATABASE_URL', 'sqlite+aiosqlite:///data/database.db')
    url = make_url(database_url)
    if not url.drivername.startswith('sqlite'):
        raise RuntimeError('Демо-наполнение поддерживает только SQLite')
    if not url.database or url.database == ':memory:':
        return 'sqlite:///:memory:'

    database_path = Path(url.database)
    if not database_path.is_absolute():
        database_path = ROOT_DIR / database_path
    database_path.parent.mkdir(parents=True, exist_ok=True)
    return f'sqlite:///{database_path}'


def ensure_schema(engine) -> None:
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        service_columns = {
            row[1]
            for row in conn.execute(text('PRAGMA table_info(services)'))
        }
        if 'is_active' not in service_columns:
            conn.execute(text('ALTER TABLE services ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1'))

        master_columns = {
            row[1]
            for row in conn.execute(text('PRAGMA table_info(masters)'))
        }
        if 'is_active' not in master_columns:
            conn.execute(text('ALTER TABLE masters ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1'))


def upsert_setting(session: Session, key: str, value: str) -> bool:
    setting = session.execute(
        select(SalonSetting).where(SalonSetting.key == key)
    ).scalar_one_or_none()
    if setting:
        if setting.value == value:
            return False
        setting.value = value
        return True

    session.add(SalonSetting(key=key, value=value))
    return True


def seed_demo_salon_sync(session: Session) -> dict[str, int]:
    summary = {
        'services_created': 0,
        'services_updated': 0,
        'masters_created': 0,
        'masters_updated': 0,
        'schedules_created': 0,
        'schedules_updated': 0,
        'settings_updated': 0,
    }

    service_map = {}
    for service_data in DEMO_SERVICES:
        service = session.execute(
            select(Service).where(Service.name == service_data['name'])
        ).scalar_one_or_none()
        if not service:
            service = Service(
                name=service_data['name'],
                duration=service_data['duration'],
                is_active=1,
            )
            session.add(service)
            session.flush()
            summary['services_created'] += 1
        else:
            changed = False
            if service.duration != service_data['duration']:
                service.duration = service_data['duration']
                changed = True
            if service.is_active != 1:
                service.is_active = 1
                changed = True
            if changed:
                summary['services_updated'] += 1
        service_map[service.name] = service

    master_map = {}
    for master_data in DEMO_MASTERS:
        master = session.execute(
            select(Master)
            .options(selectinload(Master.services))
            .where(Master.full_name == master_data['full_name'])
            .order_by(Master.id)
        ).scalars().first()
        created = False
        changed = False
        if not master:
            master = Master(
                full_name=master_data['full_name'],
                description=master_data['description'],
                is_active=1,
            )
            session.add(master)
            session.flush()
            created = True
            summary['masters_created'] += 1
        else:
            if master.description != master_data['description']:
                master.description = master_data['description']
                changed = True
            if master.is_active != 1:
                master.is_active = 1
                changed = True

        selected_services = [
            service_map[service_name]
            for service_name in master_data['services']
            if service_name in service_map
        ]
        current_service_ids = {service.id for service in master.services}
        selected_service_ids = {service.id for service in selected_services}
        if current_service_ids != selected_service_ids:
            master.services = selected_services
            changed = True
        if changed and not created:
            summary['masters_updated'] += 1
        master_map[master_data['full_name']] = master

    session.flush()

    for master_data in DEMO_MASTERS:
        master = master_map[master_data['full_name']]
        working_days = set(master_data['working_days'])
        for day_of_week in range(7):
            schedule = session.execute(
                select(Schedule).where(
                    Schedule.master_id == master.id,
                    Schedule.day_of_week == day_of_week,
                )
            ).scalar_one_or_none()
            is_working = 1 if day_of_week in working_days else 0
            if is_working:
                start_time = time.fromisoformat(master_data['start_time'])
                end_time = time.fromisoformat(master_data['end_time'])
                lunch_start = time.fromisoformat(master_data['lunch_start'])
                lunch_end = time.fromisoformat(master_data['lunch_end'])
            else:
                start_time = time(0, 0)
                end_time = time(0, 0)
                lunch_start = None
                lunch_end = None

            if not schedule:
                schedule = Schedule(
                    master_id=master.id,
                    day_of_week=day_of_week,
                    start_time=start_time,
                    end_time=end_time,
                    is_working=is_working,
                    lunch_start=lunch_start,
                    lunch_end=lunch_end,
                )
                session.add(schedule)
                summary['schedules_created'] += 1
                continue

            changed = False
            for field, value in (
                ('start_time', start_time),
                ('end_time', end_time),
                ('is_working', is_working),
                ('lunch_start', lunch_start),
                ('lunch_end', lunch_end),
            ):
                if getattr(schedule, field) != value:
                    setattr(schedule, field, value)
                    changed = True
            if changed:
                summary['schedules_updated'] += 1

    if upsert_setting(session, SALON_ADDRESS_SETTING_KEY, DEFAULT_SALON_ADDRESS):
        summary['settings_updated'] += 1
    if upsert_setting(session, SLOT_INTERVAL_SETTING_KEY, str(DEFAULT_SLOT_INTERVAL)):
        summary['settings_updated'] += 1

    session.commit()
    return summary


def main() -> None:
    engine = create_engine(get_sync_database_url())
    ensure_schema(engine)
    with Session(engine) as session:
        summary = seed_demo_salon_sync(session)
    print('Демо-салон готов')
    print(f'Услуги: добавлено {summary["services_created"]}, обновлено {summary["services_updated"]}')
    print(f'Мастера: добавлено {summary["masters_created"]}, обновлено {summary["masters_updated"]}')
    print(f'Расписание: добавлено {summary["schedules_created"]}, обновлено {summary["schedules_updated"]}')
    print(f'Настройки: обновлено {summary["settings_updated"]}')


if __name__ == '__main__':
    main()
