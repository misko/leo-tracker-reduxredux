import unittest
from compare import compare


class ComparisonTests(unittest.TestCase):
    def test_tolerated_rounding(self):
        self.assertLess(compare({"score_hz": 3.0}, {"score_hz": 3.0000001}), 1e-6)

    def test_tau_is_exact_even_when_encoded_as_float(self):
        with self.assertRaises(ValueError):
            compare({"tau_s": 1.0}, {"tau_s": 1.0000001})

    def test_rejects_nonfinite_on_either_side(self):
        for value in (float("nan"), float("inf"), -float("inf")):
            for a, b in ((value, 1.0), (1.0, value)):
                with self.assertRaises(ValueError):
                    compare(a, b)

    def test_rejects_changed_identity_or_structure(self):
        for a, b in (({"id": 1}, {"id": 2}), ([1], []),
                     ({"id": 1}, {"other": 1}), (1, 1.0), (1.0, 1.01)):
            with self.assertRaises(ValueError):
                compare(a, b)


if __name__ == "__main__":
    unittest.main()
