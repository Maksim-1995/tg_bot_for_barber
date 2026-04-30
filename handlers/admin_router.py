from datetime import time

from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from filters.admin_filter import IsAdmin
from database import async_session_maker
from services.db_service import add_service, add_master, get_services, set_master_schedule, get_future_appointments


admin_router = Router()
admin_router.message.filter(IsAdmin())


@admin_router.message(Command('add_service'))
async def cmd_add_service(message: types.Message, state: FSMContext):
    # Ожидаем сообщение вида: /add_service Стрижка 30.
    args = message.text.split(maxsplit=2)
    if len(args) < 3:
        await message.reply('Используйте: /add_service <название> <длительность в минутах>')
        return
    name = args[1]
    try:
        duration = int(args[2])
    except ValueError:
        await message.reply('Длительность должна быть числом (минуты)')
        return
    async with async_session_maker() as session:
        await add_service(session, name, duration)
    await message.reply(f"Услуга '{name}' добавлена (длительность {duration} мин)")

@admin_router.message(Command('add_master'))
async def cmd_add_master(message: types.Message, state: FSMContext):
    # /add_master Анна 'Стаж 5 лет' 1,2.
    # Номер услуги (ID) берём через запятую.
    try:
        # Упрощённый парсинг: имя, описание в кавычках, список ID.
        parts = message.text.split(maxsplit=2)
        if len(parts) < 3:
            raise ValueError
        full_name = parts[1]
        # Ищем описание и список услуг.
        rest = parts[2]
        desc_start = rest.find('"')
        desc_end = rest.find('"', desc_start+1)
        if desc_start == -1 or desc_end == -1:
            raise ValueError
        description = rest[desc_start+1:desc_end]
        ids_str = rest[desc_end+1:].strip()
        service_ids = [int(x) for x in ids_str.split(',') if x.strip()]
    except Exception:
        await message.reply("Формат: /add_master Имя 'Описание' id_услуги1,id_услуги2\n"
                            "Например: /add_master Анна 'Стаж 5 лет' 1,2")
        return
    async with async_session_maker() as session:
        await add_master(session, full_name, description, service_ids)
    await message.reply(f"Мастер '{full_name}' добавлен с услугами {service_ids}")

@admin_router.message(Command('list_services'))
async def cmd_list_services(message: types.Message):
    async with async_session_maker() as session:
        services = await get_services(session)
        if not services:
            await message.reply('Услуги ещё не добавлены.')
            return
        text = 'Список услуг:\n' + '\n'.join(
            f'{s.id}. {s.name} ({s.duration} мин)' for s in services)
        await message.reply(text)

@admin_router.message(Command('set_schedule'))
async def cmd_set_schedule(message: types.Message):
    """
    Формат: /set_schedule master_id день_недели начало конец [обед_начало обед_конец].
    
    День недели: 0=ПН, 6=ВС. Время в формате ЧЧ:ММ.
    Пример: /set_schedule 1 0 10:00 20:00 14:00 15:00
    """
    parts = message.text.split()
    if len(parts) < 5:
        await message.reply('Используйте: /set_schedule <master_id> <день_недели> <начало> <конец> [обед_начало обед_конец]')
        return
    try:
        master_id = int(parts[1])
        day_of_week = int(parts[2])
        start_time = time.fromisoformat(parts[3])
        end_time = time.fromisoformat(parts[4])
        if not (0 <= day_of_week <= 6):
            raise ValueError
        lunch_start = None
        lunch_end = None
        if len(parts) >= 7:
            lunch_start = time.fromisoformat(parts[5])
            lunch_end = time.fromisoformat(parts[6])
        async with async_session_maker() as session:
            await set_master_schedule(session, master_id, day_of_week, start_time, end_time, lunch_start, lunch_end)
        await message.reply(f'Расписание для мастера {master_id} обновлено.')
    except Exception as e:
        await message.reply(f'Ошибка: {e}. Проверьте формат.')

@admin_router.message(Command('view_bookings'))
async def cmd_view_bookings(message: types.Message):
    """Показать все будущие записи."""
    async with async_session_maker() as session:
        appointments = await get_future_appointments(session)
    if not appointments:
        await message.reply('Будущих записей нет.')
        return
    response_lines = ['Предстоящие записи:']
    for app in appointments:
        response_lines.append(
            f"• {app.date_time.strftime('%d.%m.%Y %H:%M')} — "
            f"{app.service.name} у {app.master.full_name}, "
            f"клиент: {app.user.full_name} ({app.user.phone_number})"
        )
        if app.comment:
            response_lines.append(f'  Комментарий: {app.comment}')
    await message.reply('\n'.join(response_lines))
