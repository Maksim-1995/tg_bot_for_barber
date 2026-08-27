"""Точка входа Telegram-бота и запуск polling."""

import asyncio

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError

from config import settings
from database import engine
from models import Base
from handlers.user_router import user_router
from handlers.admin_router import admin_router
from utils.logger import setup_logger


# Инициализация логгера.
logger = setup_logger('barbershop_bot')


async def init_db():
    """Создаёт таблицы в БД, если их нет."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await run_sqlite_migrations(conn)


async def run_sqlite_migrations(conn):
    """Минимальные миграции для существующей SQLite-базы без Alembic."""
    if not make_url(settings.DATABASE_URL).drivername.startswith('sqlite'):
        return

    columns_result = await conn.execute(text('PRAGMA table_info(appointments)'))
    appointment_columns = {row[1] for row in columns_result}

    if 'client_name' not in appointment_columns:
        await conn.execute(
            text("ALTER TABLE appointments ADD COLUMN client_name VARCHAR NOT NULL DEFAULT ''")
        )
    if 'client_phone' not in appointment_columns:
        await conn.execute(
            text("ALTER TABLE appointments ADD COLUMN client_phone VARCHAR NOT NULL DEFAULT ''")
        )
    if 'status' not in appointment_columns:
        await conn.execute(
            text("ALTER TABLE appointments ADD COLUMN status VARCHAR NOT NULL DEFAULT 'active'")
        )
    if 'cancelled_at' not in appointment_columns:
        await conn.execute(
            text('ALTER TABLE appointments ADD COLUMN cancelled_at DATETIME')
        )
    if 'cancel_reason' not in appointment_columns:
        await conn.execute(
            text('ALTER TABLE appointments ADD COLUMN cancel_reason VARCHAR')
        )
    if 'cancelled_by_admin_id' not in appointment_columns:
        await conn.execute(
            text('ALTER TABLE appointments ADD COLUMN cancelled_by_admin_id INTEGER')
        )

    service_columns_result = await conn.execute(text('PRAGMA table_info(services)'))
    service_columns = {row[1] for row in service_columns_result}
    if 'is_active' not in service_columns:
        await conn.execute(
            text('ALTER TABLE services ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1')
        )

    master_columns_result = await conn.execute(text('PRAGMA table_info(masters)'))
    master_columns = {row[1] for row in master_columns_result}
    if 'is_active' not in master_columns:
        await conn.execute(
            text('ALTER TABLE masters ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1')
        )

    await conn.execute(text("""
        UPDATE appointments
        SET client_name = COALESCE(
            (SELECT users.full_name FROM users WHERE users.id = appointments.user_id),
            ''
        )
        WHERE client_name = ''
    """))
    await conn.execute(text("""
        UPDATE appointments
        SET client_phone = COALESCE(
            (SELECT users.phone_number FROM users WHERE users.id = appointments.user_id),
            ''
        )
        WHERE client_phone = ''
    """))

    index_statements = [
        'CREATE UNIQUE INDEX IF NOT EXISTS uq_services_name ON services (name)',
        (
            'CREATE UNIQUE INDEX IF NOT EXISTS uq_schedules_master_day '
            'ON schedules (master_id, day_of_week)'
        ),
        (
            'CREATE INDEX IF NOT EXISTS ix_appointments_master_period '
            'ON appointments (master_id, date_time, end_time)'
        ),
    ]
    await conn.execute(text('DROP INDEX IF EXISTS uq_appointments_master_start'))
    for statement in index_statements:
        try:
            await conn.execute(text(statement))
        except SQLAlchemyError as error:
            logger.warning('Не удалось создать индекс SQLite: %s', error)


async def main():
    """Инициализирует БД, бота, роутеры и запускает polling."""
    # 1. Инициализация БД.
    await init_db()
    logger.info('База данных инициализирована')

    # 2. Инициализация бота.
    bot = Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher()

    # 3. Подключаем роутеры.
    dp.include_router(user_router)
    dp.include_router(admin_router)

    # 4. Запуск поллинга.
    logger.info('Бот запущен и готов к работе')
    await dp.start_polling(bot)


async def run_bot():
    """Перезапускает polling после временных ошибок."""
    while True:
        try:
            await main()
        except Exception as error:
            logger.error('Ошибка запуска бота: %s', error)
            logger.info('Повторное подключение через 30 секунд...')
            await asyncio.sleep(30)


if __name__ == '__main__':
    try:
        asyncio.run(run_bot())
    except KeyboardInterrupt:
        logger.info('Бот остановлен вручную')
