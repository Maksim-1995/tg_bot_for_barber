from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError


async def create_appointment(
    session,
    user_id,
    master_id,
    service_id,
    date_time,
    comment=None
):
    try:
        async with session.begin():

            service = await session.get(Service, service_id)

            if not service:
                raise ValueError('Услуга не найдена')

            end_time = (
                date_time +
                timedelta(minutes=service.duration)
            )

            collision_query = select(Appointment).where(
                Appointment.master_id == master_id,
                Appointment.date_time < end_time,
                Appointment.end_time > date_time
            )

            collision = await session.execute(collision_query)

            if collision.scalars().first():
                raise ValueError('Это время уже занято')

            appointment = Appointment(
                user_id=user_id,
                master_id=master_id,
                service_id=service_id,
                date_time=date_time,
                end_time=end_time,
                comment=comment
            )

            session.add(appointment)

        return appointment

    except SQLAlchemyError:
        await session.rollback()
        raise
