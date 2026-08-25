import os
import unittest

os.environ.setdefault('BOT_TOKEN', 'test-token')
os.environ.setdefault('ADMIN_IDS', '1')

from services.db_service import DEMO_MASTERS, DEMO_SERVICES, validate_slot_interval


class SalonSettingsTests(unittest.TestCase):
    def test_validate_slot_interval_accepts_supported_values(self):
        self.assertEqual(validate_slot_interval('30'), 30)
        self.assertEqual(validate_slot_interval(60), 60)

    def test_validate_slot_interval_rejects_unsupported_values(self):
        for value in ('bad', 15, 45, 90):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    validate_slot_interval(value)

    def test_demo_salon_has_full_staff(self):
        self.assertGreaterEqual(len(DEMO_SERVICES), 6)
        self.assertGreaterEqual(len(DEMO_MASTERS), 4)

    def test_demo_masters_reference_existing_services(self):
        service_names = {service['name'] for service in DEMO_SERVICES}

        for master in DEMO_MASTERS:
            with self.subTest(master=master['full_name']):
                self.assertTrue(set(master['services']).issubset(service_names))
                self.assertTrue(master['working_days'])


if __name__ == '__main__':
    unittest.main()
