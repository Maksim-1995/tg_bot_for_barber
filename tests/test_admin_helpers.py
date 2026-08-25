import os
import unittest
from datetime import date, time

os.environ.setdefault('BOT_TOKEN', 'test-token')
os.environ.setdefault('ADMIN_IDS', '1')

from handlers.admin_router import (
    admin_after_action_kb,
    admin_bookings_menu_kb,
    admin_closed_dates_menu_kb,
    admin_main_menu_kb,
    admin_masters_menu_kb,
    admin_schedule_menu_kb,
    admin_services_menu_kb,
    parse_admin_date,
    parse_callback_action,
    parse_callback_date,
    parse_callback_int,
    parse_callback_slot,
    parse_slot_time,
    parse_time_range,
)


def keyboard_callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row]


class AdminHelperTests(unittest.TestCase):
    def test_parse_admin_date(self):
        self.assertEqual(parse_admin_date('2026-12-31'), date(2026, 12, 31))
        self.assertEqual(parse_admin_date('31.12.2026'), date(2026, 12, 31))

    def test_parse_time_range(self):
        self.assertEqual(parse_time_range('10:00-20:00'), (time(10, 0), time(20, 0)))
        self.assertEqual(parse_time_range('10:00 20:00'), (time(10, 0), time(20, 0)))

    def test_admin_main_menu_callbacks(self):
        callbacks = keyboard_callbacks(admin_main_menu_kb())
        self.assertEqual(
            callbacks,
            [
                'admin_menu_services',
                'admin_menu_masters',
                'admin_menu_schedule',
                'admin_menu_bookings',
                'admin_menu_closed_dates',
            ],
        )

    def test_admin_submenus_have_back_button(self):
        submenus = [
            admin_services_menu_kb(),
            admin_masters_menu_kb(),
            admin_schedule_menu_kb(),
            admin_bookings_menu_kb(),
            admin_closed_dates_menu_kb(),
        ]
        for markup in submenus:
            self.assertIn('admin_menu_main', keyboard_callbacks(markup))

    def test_admin_after_action_callbacks(self):
        callbacks = keyboard_callbacks(admin_after_action_kb('admin_menu_services', 'К услугам'))
        self.assertEqual(callbacks, ['admin_menu_services', 'admin_menu_main'])

    def test_parse_callback_int(self):
        self.assertEqual(parse_callback_int('admin_edit_service_42', 'admin_edit_service_'), 42)
        self.assertIsNone(parse_callback_int('admin_edit_service_bad', 'admin_edit_service_'))
        self.assertIsNone(parse_callback_int('wrong_42', 'admin_edit_service_'))

    def test_parse_callback_date(self):
        self.assertEqual(
            parse_callback_date('admin_booking_date_2026-12-31', 'admin_booking_date_'),
            date(2026, 12, 31),
        )
        self.assertIsNone(parse_callback_date('admin_booking_date_bad', 'admin_booking_date_'))

    def test_parse_callback_action(self):
        self.assertEqual(
            parse_callback_action('admin_booking_action_cancel', 'admin_booking_action_', {'cancel'}),
            'cancel',
        )
        self.assertIsNone(
            parse_callback_action('admin_booking_action_delete', 'admin_booking_action_', {'cancel'}),
        )

    def test_parse_slot_time(self):
        self.assertEqual(parse_slot_time('10:30'), time(10, 30))
        self.assertEqual(parse_callback_slot('admin_booking_slot_10:30', 'admin_booking_slot_'), time(10, 30))
        self.assertIsNone(parse_slot_time('10:30:15'))
        self.assertIsNone(parse_slot_time('bad'))


if __name__ == '__main__':
    unittest.main()
