import unittest

from study import gate


class Tests(unittest.TestCase):
    def test_missing_bound_never_certifies(self):
        self.assertEqual(gate(0)["status"], "unverified_reference_bound")

    def test_strict_threshold_and_triangle_bound(self):
        self.assertEqual(gate(400, 599)["true_error_upper_bound_m"], 999)
        self.assertEqual(gate(400, 599)["status"], "below_threshold")
        self.assertEqual(gate(400, 600)["status"], "not_certified")
        with self.assertRaises(ValueError):
            gate(400, -1)


if __name__ == "__main__":
    unittest.main()
