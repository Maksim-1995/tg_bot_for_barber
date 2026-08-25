"""Состояния конечного автомата для процесса записи."""

from aiogram.fsm.state import State, StatesGroup


class BookingForm(StatesGroup):
    """Состояния для процесса записи."""

    waiting_for_service = State()
    waiting_for_master = State()
    waiting_for_date = State()
    waiting_for_time = State()
    waiting_for_name = State()
    waiting_for_phone = State()
    waiting_for_comment = State()
    waiting_for_confirmation = State()


class AdminServiceForm(StatesGroup):
    """Состояния добавления услуги администратором."""

    waiting_for_name = State()
    waiting_for_duration = State()


class AdminEditServiceForm(StatesGroup):
    """Состояния редактирования услуги."""

    waiting_for_service = State()
    waiting_for_action = State()
    waiting_for_name = State()
    waiting_for_duration = State()


class AdminMasterForm(StatesGroup):
    """Состояния добавления мастера администратором."""

    waiting_for_name = State()
    waiting_for_description = State()
    waiting_for_services = State()


class AdminEditMasterForm(StatesGroup):
    """Состояния редактирования мастера."""

    waiting_for_master = State()
    waiting_for_action = State()
    waiting_for_name = State()
    waiting_for_description = State()
    waiting_for_services = State()


class AdminScheduleForm(StatesGroup):
    """Состояния настройки расписания мастера."""

    waiting_for_master = State()
    waiting_for_day = State()
    waiting_for_action = State()
    waiting_for_work_hours = State()
    waiting_for_lunch = State()


class AdminClosedDateForm(StatesGroup):
    """Состояния управления ручными выходными датами."""

    waiting_for_date = State()
    waiting_for_reason = State()


class AdminBookingManageForm(StatesGroup):
    """Состояния управления существующей записью."""

    waiting_for_appointment = State()
    waiting_for_action = State()
    waiting_for_reschedule_date = State()
    waiting_for_reschedule_time = State()
    waiting_for_cancel_reason = State()


class AdminCreateBookingForm(StatesGroup):
    """Состояния ручного создания записи администратором."""

    waiting_for_service = State()
    waiting_for_master = State()
    waiting_for_date = State()
    waiting_for_time = State()
    waiting_for_name = State()
    waiting_for_phone = State()
    waiting_for_comment = State()
    waiting_for_confirmation = State()
