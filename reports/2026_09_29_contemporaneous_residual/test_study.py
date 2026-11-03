import copy
import unittest

import numpy as np
from study import error, predictor


def case(number, rx=0, drift=2):
    t = np.arange(20, dtype=float)
    return dict(
        session_id="scan",
        track_id=str((number, rx)),
        number=number,
        receiver_id=rx,
        rf_hz=11.2e9,
        times=t.tolist(),
        residual=(7 + drift * t).tolist(),
        mask=(t % 2 == 0).tolist(),
    )


class TransferTests(unittest.TestCase):
    def test_recovery_and_candidate_exclusion(self):
        target = case(0)
        donors = [case(i) for i in range(1, 4)] + [case(0, drift=999)]
        self.assertEqual(predictor(target, donors, True)["slope"], 2)
        self.assertEqual(error(target, 2), 0)
        self.assertIsNone(predictor(target, donors[:2], True))

    def test_held_isolation_and_order(self):
        target = case(0)
        donors = [case(i) for i in range(1, 4)]
        expected = predictor(target, donors, True)
        changed = copy.deepcopy(donors)
        for d in changed:
            d["residual"][1::2] = [1e9] * 10
        self.assertEqual(predictor(target, changed[::-1], True), expected)

    def test_lane_and_temporal_isolation(self):
        target = case(0)
        donors = [case(i, rx=1) for i in range(1, 4)]
        self.assertIsNone(predictor(target, donors, True))
        self.assertEqual(predictor(target, donors, False)["slope"], 2)
        donors[0]["times"] = (np.arange(20) + 100).tolist()
        self.assertIsNone(predictor(target, donors, False))
        donors[0] = case(1, rx=1)
        donors[0]["rf_hz"] += 1
        self.assertIsNone(predictor(target, donors, False))


if __name__ == "__main__":
    unittest.main()
