import asyncio
import logging
import os
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from config import settings
from database import engine
from models import Base
from handlers.user_router import user_router
from handlers.admin_router import admin_router


# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def init_db():
    """Создаёт таблицы в БД, если их нет."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def main():
    # 1. Инициализация БД
    Path("data").mkdir(exist_ok=True)
    await init_db()
    logger.info("База данных инициализирована")

    # 2. Инициализация бота и диспетчера
    bot = Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher()

    # 3. Подключаем роутеры
    dp.include_router(user_router)
    dp.include_router(admin_router)

    # 4. Запуск поллинга
    logger.info("Бот запущен и готов к работе")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот остановлен вручную")
