import unittest

from utils.validators import (
    normalize_phone,
    sanitize_comment,
    validate_name,
    validate_phone,
)


class ValidatorTests(unittest.TestCase):
    def test_normalize_phone(self):
        self.assertEqual(normalize_phone('8 (999) 123-45-67'), '+79991234567')
        self.assertEqual(normalize_phone('79991234567'), '+79991234567')
        self.assertEqual(normalize_phone('+7 999 123-45-67'), '+79991234567')

    def test_validate_phone(self):
        self.assertEqual(validate_phone('+79991234567'), (True, None))
        self.assertEqual(validate_phone('79991234567'), (True, None))
        self.assertFalse(validate_phone('123')[0])

    def test_validate_name(self):
        self.assertEqual(validate_name('Анна-Мария'), (True, None))
        self.assertFalse(validate_name('A1')[0])

    def test_sanitize_comment(self):
        self.assertEqual(sanitize_comment('  без лака  '), ('без лака', None))
        self.assertIsNotNone(sanitize_comment('x' * 201)[1])


if __name__ == '__main__':
    unittest.main()
