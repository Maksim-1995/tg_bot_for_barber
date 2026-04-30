from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, DateTime, Time, ForeignKey, Table
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


master_service = Table(
    'master_service',
    Base.metadata,
    Column('master_id', Integer, ForeignKey('masters.id'), primary_key=True),
    Column('service_id', Integer, ForeignKey('services.id'), primary_key=True),
)


class Service(Base):
    """Класс для услуг, которые предоставляет салон."""

    __tablename__ = 'services'
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    duration = Column(Integer, nullable=False)  # в минутах.


class Master(Base):
    """Класс для мастеров, которые работают в салоне."""

    __tablename__ = 'masters'
    id = Column(Integer, primary_key=True, autoincrement=True)
    full_name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    # Услуги, которые может выполнять мастер.
    services = relationship('Service', secondary=master_service, backref='masters')


class Schedule(Base):
    """Расписание работы мастера по дням недели."""

    __tablename__ = 'schedules'
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
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    master_id = Column(Integer, ForeignKey('masters.id'), nullable=False)
    service_id = Column(Integer, ForeignKey('services.id'), nullable=False)
    date_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)
    comment = Column(String, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    user = relationship('User', backref='appointments')
    master = relationship('Master', backref='appointments')
    service = relationship('Service', backref='appointments')
