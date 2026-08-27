"""SQLAlchemy-модели домена парикмахерской."""

from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Table,
    Time,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    """Базовый класс декларативных моделей SQLAlchemy."""


master_service = Table(
    'master_service',
    Base.metadata,
    Column('master_id', Integer, ForeignKey('masters.id'), primary_key=True),
    Column('service_id', Integer, ForeignKey('services.id'), primary_key=True),
)


class Service(Base):
    """Класс для услуг, которые предоставляет салон."""

    __tablename__ = 'services'
    __table_args__ = (UniqueConstraint('name', name='uq_services_name'),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    duration = Column(Integer, nullable=False)  # в минутах.
    is_active = Column(Integer, default=1, nullable=False)


class Master(Base):
    """Класс для мастеров, которые работают в салоне."""

    __tablename__ = 'masters'
    id = Column(Integer, primary_key=True, autoincrement=True)
    full_name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    is_active = Column(Integer, default=1, nullable=False)
    # Услуги, которые может выполнять мастер.
    services = relationship('Service', secondary=master_service, backref='masters')


class Schedule(Base):
    """Расписание работы мастера по дням недели."""

    __tablename__ = 'schedules'
    __table_args__ = (
        UniqueConstraint('master_id', 'day_of_week', name='uq_schedules_master_day'),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    master_id = Column(Integer, ForeignKey('masters.id'), nullable=False)
    day_of_week = Column(Integer, nullable=False)  # 0=ПН, 6=ВС.
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    is_working = Column(Integer, default=1)
    lunch_start = Column(Time, nullable=True)   # Начало обеда (если есть).
    lunch_end = Column(Time, nullable=True)     # Конец обеда.
    master = relationship('Master', backref='schedules')


class User(Base):
    """Клиент бота."""

    __tablename__ = 'users'
    id = Column(Integer, primary_key=True, autoincrement=True)
    telegram_id = Column(Integer, unique=True, nullable=False)
    full_name = Column(String, nullable=True)
    phone_number = Column(String, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class Appointment(Base):
    """Запись клиента на услугу к мастеру в определённое время."""

    __tablename__ = 'appointments'
    __table_args__ = (
        Index('ix_appointments_master_period', 'master_id', 'date_time', 'end_time'),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    master_id = Column(Integer, ForeignKey('masters.id'), nullable=False)
    service_id = Column(Integer, ForeignKey('services.id'), nullable=False)
    client_name = Column(String, nullable=False)
    client_phone = Column(String, nullable=False)
    date_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)
    status = Column(String, default='active', nullable=False)
    comment = Column(String, nullable=True)
    cancelled_at = Column(DateTime, nullable=True)
    cancel_reason = Column(String, nullable=True)
    cancelled_by_admin_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    user = relationship('User', backref='appointments')
    master = relationship('Master', backref='appointments')
    service = relationship('Service', backref='appointments')


class ClosedDate(Base):
    """Ручной выходной или праздничный день салона."""

    __tablename__ = 'closed_dates'
    __table_args__ = (UniqueConstraint('date', name='uq_closed_dates_date'),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(Date, nullable=False)
    reason = Column(String, nullable=True)


class SalonSetting(Base):
    """Настройка салона, которую можно менять из админки."""

    __tablename__ = 'salon_settings'
    __table_args__ = (UniqueConstraint('key', name='uq_salon_settings_key'),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    key = Column(String, nullable=False)
    value = Column(String, nullable=False)
