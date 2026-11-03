import unittest

from run import accept


class GateTest(unittest.TestCase):
    def test_requires_both_scales(self):
        self.assertTrue(accept(True, 999, 999))
        self.assertFalse(accept(True, 999, 1000))
        self.assertFalse(accept(True, 1000, 999))

    def test_numerical_failure_abstains(self):
        self.assertFalse(accept(False, 1, 1))
        self.assertFalse(accept(True, float("nan"), 1))
        self.assertFalse(accept(True, 1, float("inf")))


if __name__ == "__main__":
    unittest.main()
