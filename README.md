# Telegram-бот для записи в парикмахерскую «Народная цирюльня»

## Описание проекта

Telegram-бот для автоматизации записи клиентов в парикмахерскую «Народная цирюльня».

Бот позволяет клиентам самостоятельно записываться к мастерам через Telegram, просматривать доступное время и получать подтверждение записи без участия администратора.

Для сотрудников предусмотрены административные команды управления мастерами, расписанием и записями клиентов.

Бот разработан на Python с использованием библиотеки Aiogram и базы данных SQLite.
---

## Бот

Telegram:

@ai_bar_baros_bot

Пример: images/tg_bot.jpg


---

## Возможности

### Для клиентов

* Просмотр списка мастеров.
* Просмотр доступных дат и времени.
* Онлайн-запись к мастеру.
* Получение подтверждения записи.
* Удобный интерфейс через Telegram.

### Для администратора

* Добавление новых мастеров.
* Настройка рабочего расписания.
* Просмотр записей клиентов.
* Управление расписанием мастеров.

---

## Стек технологий

* Python 3.11+
* Aiogram 3
* SQLAlchemy
* SQLite
* Docker
* GitHub Actions (CI/CD)

---

## Структура проекта

```tg_bot_for_barber
├── alembic
|  └── env.py
├── bot.py
├── cat
├── config.py
├── create_appointment.py
├── data
|  └── database.db
├── database.py
├── Dockerfile
├── filters
|  ├── admin_filter.py
|  └── __pycache__
├── handlers
|  ├── admin_router.py
|  ├── fsm.py
|  ├── user_router.py
|  ├── __init__.py
|  └── __pycache__
├── keyboards
|  ├── inline_kb.py
|  ├── reply_kb.py
|  ├── __init__.py
|  └── __pycache__
├── logs
|  └── bot.log
├── models.py
├── README.md
├── requirements.txt
├── services
|  ├── calendar_service.py
|  ├── db_service.py
|  ├── notifications.py
|  ├── __init__.py
|  └── __pycache__
├── utils
|  ├── constants.py
|  ├── datetime.py
|  ├── logger.py
|  ├── validators.py
|  ├── __init__.py
|  └── __pycache__
```

---

## Установка и запуск

### 1. Клонирование репозитория

```bash
git clone https://github.com/Maksim-1995/tg_bot_for_barber.git
cd tg_bot_for_barber
```

---

### 2. Создание виртуального окружения

Linux/macOS:

```bash
python3 -m venv venv
source venv/bin/activate
```

Windows:

```powershell
python -m venv venv
venv\Scripts\activate
```

---

### 3. Установка зависимостей

```bash
pip install -r requirements.txt
```

---

### 4. Настройка переменных окружения

Создайте файл `.env` по примеру файла `.env.example`.

Пример:

```env
BOT_TOKEN=your_telegram_bot_token
ADMIN_ID=123456789
DATABASE_URL=sqlite+aiosqlite:///data/barbershop.db
```

---

### 5. Запуск проекта

```bash
python bot.py
```

После успешного запуска в консоли появится сообщение:

```text
База данных инициализирована
Бот запущен и готов к работе
```

---

## Запуск через Docker

### Сборка образа

```bash
docker build -t barber_bot .
```

### Запуск контейнера

```bash
docker run -d \
  --name barber_bot \
  --restart unless-stopped \
  --env-file .env \
  barber_bot
```

### Просмотр логов

```bash
docker logs -f barber_bot
```

---

## Административные команды

Команды доступны только администраторам.

### Добавление мастера

```text
/add_master
```

Позволяет добавить нового мастера в систему.

---

### Настройка расписания

```text
/set_schedule
```

Используется для создания и изменения расписания работы мастеров.

---

### Просмотр записей

```text
/view_bookings
```

Показывает список всех записей клиентов.

---

## Пользовательский сценарий

1. Клиент открывает бота.
2. Выбирает мастера.
3. Выбирает дату.
4. Выбирает свободное время.
5. Подтверждает запись.
6. Информация сохраняется в базе данных.
7. Администратор может просмотреть запись через команду `/view_bookings`.

---

## CI/CD

Проект поддерживает автоматический деплой через GitHub Actions.

После каждого пуша в ветку `main`:

1. Собирается Docker-образ.
2. Образ публикуется в Docker Hub.
3. Выполняется обновление контейнера на сервере.

---

## Переменные окружения

| Переменная   | Описание                         |
| ------------ | -------------------------------- |
| BOT_TOKEN    | Токен Telegram-бота              |
| ADMIN_ID     | Telegram ID администратора       |
| DATABASE_URL | Строка подключения к базе данных |


---

## Автор

Максим

GitHub:

https://github.com/Maksim-1995

---

## Планы по развитию

* Уведомления о предстоящей записи.
* Отмена и перенос записи.
* Несколько филиалов парикмахерской.
* Интеграция с Google Calendar.
* Статистика посещений.
* Панель администратора.

---
