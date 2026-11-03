import copy
import unittest

import numpy as np
from clock_transfer import predict


def case(n, rf=11.2e9, s=2):
    t = np.arange(20.0)
    return dict(
        number=n,
        track_id=str(n),
        rf_hz=rf,
        receiver_id=0,
        session_id="scan",
        times=t.tolist(),
        residual=(3 + s * t).tolist(),
        mask=(t % 2 == 0).tolist(),
    )


class ClockTests(unittest.TestCase):
    def test_physical_scaling(self):
        target = case(0)
        donors = [case(n, 10e9, 11.2 / 10 * 2) for n in range(1, 4)]
        result, counts = predict(target, donors)
        self.assertAlmostEqual(result["additive"], 2)
        self.assertAlmostEqual(result["fractional"], 2.24)
        self.assertEqual(counts["usable"], 3)

    def test_isolation(self):
        target = case(0)
        donors = [case(n, 10e9) for n in range(1, 4)]
        expected = predict(target, donors)
        changed = copy.deepcopy(donors)
        for d in changed:
            d["residual"][1::2] = [1e9] * 10
        self.assertEqual(predict(target, changed[::-1] + [case(0, 10e9, 999)]), expected)
        self.assertIsNone(predict(target, donors[:2])[0])
        self.assertIsNone(predict(target, [case(n) for n in range(1, 4)])[0])
        self.assertIsNone(predict(target, donors, False)[0])

    def test_time_support(self):
        donors = [case(n, 10e9) for n in range(1, 4)]
        donors[0]["times"] = (np.arange(20.0) + 100).tolist()
        result, counts = predict(case(0), donors)
        self.assertIsNone(result)
        self.assertEqual(counts, dict(other_rf=3, overlap=2, usable=2))


if __name__ == "__main__":
    unittest.main()
