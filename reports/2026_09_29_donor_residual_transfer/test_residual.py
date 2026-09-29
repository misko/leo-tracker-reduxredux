import unittest

import numpy as np
from residual import errors, shape, transfer


class Tests(unittest.TestCase):
    def test_exact_slope_and_held_isolation(self):
        t = np.arange(12.0)
        m = t < 8
        e = 30 + 2 * t
        s = shape(t, e, m)
        self.assertAlmostEqual(s["slope"], 2.0)
        altered = e.copy()
        altered[~m] += 99999
        self.assertEqual(s, shape(t, altered, m))
        target = dict(times=t, residual=e, mask=m, shape=s)
        self.assertAlmostEqual(errors(target, 2.0)["held_median_abs"], 0.0)
        self.assertGreater(errors(target, 0.0)["held_median_abs"], 0.0)

    def test_short_training(self):
        self.assertIsNone(shape(np.arange(8.0), np.arange(8.0), np.arange(8.0) < 4))

    def test_causal_matched_groups(self):
        target = dict(start_utc_ns=10, receiver_id="r0", rf_hz=100, number=1)
        donors = [
            dict(
                unit_id=g,
                available_utc_ns=end,
                receiver_id="r0",
                rf_hz=100,
                number=n,
                shape=dict(slope=s),
            )
            for g, end in [("a", 1), ("b", 2), ("future", 10)]
            for n, s in [(1, 2.0), (2, 8.0)]
        ]
        r = transfer(target, donors)
        self.assertEqual(r["groups"], ["a", "b"])
        self.assertEqual(r["candidate_slope"], 2.0)
        self.assertEqual(r["control_slope"], 8.0)
        self.assertIsNone(transfer(target, donors[:2]))
        for d in donors:
            d["rf_hz"] = 101
        self.assertIsNone(transfer(target, donors))


if __name__ == "__main__":
    unittest.main()
