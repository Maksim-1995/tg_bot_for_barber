"""Валидаторы для вводимых пользователем данных."""

import re


# Минимальная и максимальная длина имени.
MIN_NAME_LENGTH = 2
MAX_NAME_LENGTH = 40

# Регулярное выражение для российского номера телефона.
PHONE_PATTERN = re.compile(r'^(\+7|8|7)\d{10}$')

# Разрешённые символы в имени: буквы, пробел, дефис, апостроф.
NAME_PATTERN = re.compile(r"^[а-яёА-ЯЁA-Za-z\s\-']+$")


def validate_name(name: str) -> tuple[bool, str | None]:
    """
    Проверяет имя на допустимость.

    Возвращает:
        (True, None) если имя корректно.
        (False, сообщение_об_ошибке) если есть проблемы.
    """
    if not name or not name.strip():
        return False, 'Имя не может быть пустым.'

    stripped = name.strip()

    if len(stripped) < MIN_NAME_LENGTH:
        return False, f'Имя слишком короткое (минимум {MIN_NAME_LENGTH} символа).'

    if len(stripped) > MAX_NAME_LENGTH:
        return False, f'Имя слишком длинное (максимум {MAX_NAME_LENGTH} символов).'

    if not NAME_PATTERN.match(stripped):
        return False, 'Имя может содержать только буквы, пробелы, дефисы и апострофы.'

    return True, None


def validate_phone(phone: str) -> tuple[bool, str | None]:
    """
    Проверяет номер телефона на корректность (российский формат).

    Ожидается строка в формате +7XXXXXXXXXX или 8XXXXXXXXXX.
    """
    if not phone:
        return False, 'Номер телефона не указан.'

    cleaned = normalize_phone(phone)

    if not PHONE_PATTERN.match(cleaned):
        return False, 'Введите корректный номер телефона (+7XXXXXXXXXX, 7XXXXXXXXXX или 8XXXXXXXXXX).'

    return True, None


def normalize_phone(phone: str) -> str:
    """Приводит российский номер к виду +7XXXXXXXXXX, если это возможно."""
    cleaned = re.sub(r'[^\d+]', '', phone)
    if cleaned.startswith('8') and len(cleaned) == 11:
        return f'+7{cleaned[1:]}'
    if cleaned.startswith('7') and len(cleaned) == 11:
        return f'+{cleaned}'
    return cleaned


def sanitize_comment(comment: str, max_length: int = 200) -> tuple[str, str | None]:
    """
    Очищает и проверяет комментарий.

    Возвращает:
        (очищенный_комментарий, None) если всё хорошо.
        (оригинальный_текст, сообщение_об_ошибке) если превышена длина.
    """
    if not comment:
        return '', None

    stripped = comment.strip()

    if len(stripped) > max_length:
        return stripped, f'Комментарий слишком длинный (максимум {max_length} символов).'

    return stripped, None
