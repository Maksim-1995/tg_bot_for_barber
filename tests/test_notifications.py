import os
import unittest
from datetime import datetime
from types import SimpleNamespace

os.environ.setdefault('BOT_TOKEN', 'test-token')
os.environ.setdefault('ADMIN_IDS', '1')

from services.notifications import (
    appointment_master_name,
    appointment_service_name,
    format_client_booking_cancelled_message,
    format_client_booking_confirmed_message,
    format_client_booking_rescheduled_message,
    format_new_booking_admin_message,
    notify_booking_client,
    safe_send_message,
)


def make_appointment(**overrides):
    appointment = SimpleNamespace(
        date_time=datetime(2026, 12, 31, 10, 30),
        service=SimpleNamespace(name='Стрижка'),
        master=SimpleNamespace(full_name='Анна'),
    )
    for key, value in overrides.items():
        setattr(appointment, key, value)
    return appointment


class NotificationFormatTests(unittest.TestCase):
    def test_new_booking_admin_message_contains_comment_when_present(self):
        message = format_new_booking_admin_message(
            client_name='Иван',
            service_name='Стрижка',
            master_name='Анна',
            date_time_str='31.12.2026 в 10:30',
            phone='+375291234567',
            comment='Без машинки',
        )

        self.assertIn('🆕 Новая запись:', message)
        self.assertIn('Клиент: Иван', message)
        self.assertIn('Дата: 31.12.2026 в 10:30', message)
        self.assertIn('Комментарий: Без машинки', message)

    def test_new_booking_admin_message_skips_empty_comment(self):
        message = format_new_booking_admin_message(
            client_name='Иван',
            service_name='Стрижка',
            master_name='Анна',
            date_time_str='31.12.2026 в 10:30',
            phone='+375291234567',
            comment=None,
        )

        self.assertNotIn('Комментарий:', message)

    def test_client_booking_confirmed_message_contains_salon_address(self):
        message = format_client_booking_confirmed_message()

        self.assertIn('✅ Вы записаны!', message)
        self.assertIn('м. Отрадное Северный бульвар, д. 3, к. 2', message)

    def test_client_booking_confirmed_message_uses_custom_salon_address(self):
        message = format_client_booking_confirmed_message('Новый адрес')

        self.assertIn('Новый адрес', message)

    def test_client_booking_cancelled_message_contains_reason_when_present(self):
        message = format_client_booking_cancelled_message(
            make_appointment(),
            reason='Мастер заболел',
        )

        self.assertIn('Ваша запись на 31.12.2026 10:30', message)
        self.assertIn('(Стрижка, мастер Анна)', message)
        self.assertIn('отменена администратором.', message)
        self.assertIn('Причина: Мастер заболел', message)

    def test_client_booking_rescheduled_message_contains_new_slot(self):
        message = format_client_booking_rescheduled_message(make_appointment())

        self.assertIn('Ваша запись перенесена на 31.12.2026 10:30.', message)
        self.assertIn('Услуга: Стрижка', message)
        self.assertIn('Мастер: Анна', message)

    def test_appointment_names_have_fallbacks(self):
        appointment = make_appointment(
            service=None,
            master=None,
            service_name='Окрашивание',
            master_name='Мария',
        )

        self.assertEqual(appointment_service_name(appointment), 'Окрашивание')
        self.assertEqual(appointment_master_name(appointment), 'Мария')

    def test_appointment_names_have_safe_defaults(self):
        appointment = make_appointment(service=None, master=None)

        self.assertEqual(appointment_service_name(appointment), 'услуга')
        self.assertEqual(appointment_master_name(appointment), 'мастер')


class FakeBot:
    def __init__(self, *, should_fail: bool = False):
        self.should_fail = should_fail
        self.sent_messages = []

    async def send_message(self, chat_id, text):
        if self.should_fail:
            raise RuntimeError('send failed')
        self.sent_messages.append((chat_id, text))


class NotificationDeliveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_safe_send_message_returns_true_on_success(self):
        bot = FakeBot()

        result = await safe_send_message(bot, 42, 'Текст')

        self.assertTrue(result)
        self.assertEqual(bot.sent_messages, [(42, 'Текст')])

    async def test_safe_send_message_returns_false_on_error(self):
        bot = FakeBot(should_fail=True)

        with self.assertLogs('services.notifications', level='ERROR') as logs:
            result = await safe_send_message(bot, 42, 'Текст')

        self.assertFalse(result)
        self.assertIn('Не удалось отправить уведомление в чат 42', logs.output[0])

    async def test_notify_booking_client_skips_manual_user(self):
        bot = FakeBot()
        appointment = make_appointment(user=SimpleNamespace(telegram_id=-1))

        result = await notify_booking_client(bot, appointment, 'Текст')

        self.assertFalse(result)
        self.assertEqual(bot.sent_messages, [])

    async def test_notify_booking_client_sends_to_telegram_user(self):
        bot = FakeBot()
        appointment = make_appointment(user=SimpleNamespace(telegram_id=42))

        result = await notify_booking_client(bot, appointment, 'Текст')

        self.assertTrue(result)
        self.assertEqual(bot.sent_messages, [(42, 'Текст')])


if __name__ == '__main__':
    unittest.main()
