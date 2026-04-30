"""Настройка логирования для бота."""

import logging
import sys
from pathlib import Path
from logging.handlers import RotatingFileHandler


# Константы настройки.
LOG_DIR = Path('logs')
LOG_FILE = LOG_DIR / 'bot.log'
MAX_LOG_SIZE = 5 * 1024 * 1024  # 5 МБ.
BACKUP_COUNT = 3
LOG_FORMAT = '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
DATE_FORMAT = '%d.%m.%Y %H:%M:%S'


def setup_logger(name: str = 'barbershop_bot', level: int = logging.INFO) -> logging.Logger:
    """
    Создаёт и настраивает логгер.

    Логи выводятся в консоль и в файл с ротацией.
    """
    # Создаём папку для логов, если её нет.
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    # Корневой логгер для нашего приложения.
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Форматтер.
    formatter = logging.Formatter(fmt=LOG_FORMAT, datefmt=DATE_FORMAT)

    # Обработчик для вывода в консоль.
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # Обработчик для записи в файл с ротацией.
    file_handler = RotatingFileHandler(
        LOG_FILE,
        maxBytes=MAX_LOG_SIZE,
        backupCount=BACKUP_COUNT,
        encoding='utf-8'
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # Чтобы сообщения не дублировались от корневого логгера.
    logger.propagate = False

    return logger
