import os
import unittest
from datetime import date

os.environ.setdefault('BOT_TOKEN', 'test-token')
os.environ.setdefault('ADMIN_IDS', '1')

from handlers.user_router import (
    booking_restart_kb,
    normalize_slot_value,
    parse_prefixed_date,
    parse_prefixed_int,
    parse_slot_value,
)


def keyboard_callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row]


class UserHelperTests(unittest.TestCase):
    def test_parse_prefixed_int(self):
        self.assertEqual(parse_prefixed_int('service_10', 'service_'), 10)
        self.assertIsNone(parse_prefixed_int('service_bad', 'service_'))
        self.assertIsNone(parse_prefixed_int('wrong_10', 'service_'))

    def test_parse_prefixed_date(self):
        self.assertEqual(parse_prefixed_date('date_2026-12-31', 'date_'), date(2026, 12, 31))
        self.assertIsNone(parse_prefixed_date('date_bad', 'date_'))

    def test_parse_slot_value(self):
        self.assertEqual(normalize_slot_value('10:30'), '10:30')
        self.assertEqual(parse_slot_value('slot_10:30', 'slot_'), '10:30')
        self.assertIsNone(normalize_slot_value('10:30:15'))
        self.assertIsNone(normalize_slot_value('10:30+03:00'))
        self.assertIsNone(parse_slot_value('slot_bad', 'slot_'))

    def test_booking_restart_keyboard(self):
        self.assertEqual(keyboard_callbacks(booking_restart_kb()), ['book'])


if __name__ == '__main__':
    unittest.main()
