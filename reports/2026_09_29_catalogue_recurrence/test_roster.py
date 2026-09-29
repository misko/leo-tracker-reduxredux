import unittest

from summarize_v2 import number, raw_roster


class Tests(unittest.TestCase):
    def test_alpha_boundaries(self):
        for field, want in [
            ("00001", 1),
            ("99999", 99999),
            ("A0001", 100001),
            ("H9999", 179999),
            ("J0000", 180000),
            ("N9999", 229999),
            ("P0000", 230000),
            ("Z9999", 339999),
        ]:
            self.assertEqual(number(field), want)

    def test_invalid(self):
        for field in ("I0000", "O0000", "A000", "a0001", "A00x1"):
            with self.assertRaises(ValueError):
                number(field)

    def test_order_and_debris(self):
        payload = (
            "0 STARLINK TEST\n1 A0001 test\n2 A0001 test\n"
            "STARLINK TEST DEB\n1 12345 test\n2 12345 test\n"
            "1 99999 test\n2 99999 test\n"
        )
        self.assertEqual(raw_roster(payload), ([100001, 99999], 1))


if __name__ == "__main__":
    unittest.main()
