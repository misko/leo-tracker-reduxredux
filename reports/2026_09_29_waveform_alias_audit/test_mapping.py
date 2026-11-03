import unittest

from run import convert


class MappingTests(unittest.TestCase):
    def test_signed_alias_and_rf_scaling(self):
        for alias in (-3, 0, 2):
            rf = 10.94e9
            cached = 3200.0
            native = cached + alias / 4.4e-6
            measured = native * 11.2e9 / rf
            value, recovered = convert(measured, rf, cached)
            self.assertAlmostEqual(value, native)
            self.assertEqual(recovered, alias)

    def test_noninteger_alias_rejected(self):
        with self.assertRaises(AssertionError):
            convert(100, 11.2e9, 0)


if __name__ == "__main__":
    unittest.main()
