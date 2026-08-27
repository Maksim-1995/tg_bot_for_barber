"""Инициализация SQLAlchemy engine и фабрики async-сессий."""

from pathlib import Path

from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from config import settings


def ensure_sqlite_parent_dir(database_url: str) -> None:
    """Создаёт директорию для SQLite-файла, если используется файловая БД."""
    url = make_url(database_url)
    if not url.drivername.startswith('sqlite'):
        return
    if not url.database or url.database == ':memory:':
        return
    Path(url.database).parent.mkdir(parents=True, exist_ok=True)


ensure_sqlite_parent_dir(settings.DATABASE_URL)

engine_kwargs = {}
if make_url(settings.DATABASE_URL).drivername.startswith('sqlite'):
    engine_kwargs['connect_args'] = {'timeout': 30}

engine = create_async_engine(settings.DATABASE_URL, **engine_kwargs)
async_session_maker = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncSession:
    """Возвращает async-сессию БД для dependency-style использования."""
    async with async_session_maker() as session:
        yield session
