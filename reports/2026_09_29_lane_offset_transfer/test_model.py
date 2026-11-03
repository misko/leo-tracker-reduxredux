import unittest

import numpy as np
from model import PERIOD, circular_median, predict, wrap


class OffsetTests(unittest.TestCase):
    def test_alias_invariance(self):
        values = np.array([2.0, -30.0, 1000.0])
        np.testing.assert_allclose(
            wrap(values + np.array([2, -3, 1]) * PERIOD), wrap(values), atol=1e-9
        )

    def test_median_across_wrap_boundary(self):
        values = [PERIOD / 2 - 10, -PERIOD / 2 + 3, -PERIOD / 2 + 8]
        self.assertLess(abs(float(wrap(circular_median(values) - (-PERIOD / 2 + 3)))), 1e-8)

    def test_target_candidate_excluded_and_numbers_balanced(self):
        target = dict(session_id="a", rf_hz=11e9, receiver_id=0, track_id="t", number=1)
        donors = [
            dict(target, track_id=str(n), number=n, native_offset_hz=f)
            for n, f in [(1, 9999), (2, 10), (3, 11), (4, 12)]
        ]
        result = predict(target, donors)
        self.assertEqual(result["offset_hz"], 11)
        self.assertEqual(result["donor_numbers"], [2, 3, 4])
        self.assertIsNone(predict(target, donors[:-1]))


if __name__ == "__main__":
    unittest.main()
