import copy
import unittest

import numpy as np
from transfer import predict


def case(number=1, rx=0):
    t = np.arange(20.0)
    return dict(
        number=number,
        receiver_id=rx,
        track_id=str((number, rx)),
        session_id="s",
        rf_hz=11e9,
        times=t.tolist(),
        residual=(9 + 2 * t).tolist(),
        mask=(t % 2 == 0).tolist(),
    )


class TransferTests(unittest.TestCase):
    def test_candidate_separation(self):
        target, same, other = case(), case(rx=1), case(2, 1)
        self.assertEqual(
            predict(target, [same, other])["donors"], [dict(track_id=same["track_id"], number=1)]
        )
        self.assertEqual(
            predict(target, [same, other], False)["donors"],
            [dict(track_id=other["track_id"], number=2)],
        )
        self.assertEqual(predict(target, [same])["slope"], 2)
        self.assertIsNone(predict(target, [target]))

    def test_held_isolation(self):
        target, donor = case(), case(rx=1)
        expected = predict(target, [donor])
        changed = copy.deepcopy(donor)
        changed["residual"][1::2] = [1e9] * 10
        self.assertEqual(predict(target, [changed]), expected)

    def test_support(self):
        target, donor = case(), case(rx=1)
        donor["rf_hz"] += 1
        self.assertIsNone(predict(target, [donor]))
        donor = case(rx=1)
        donor["times"] = (np.arange(20.0) + 100).tolist()
        self.assertIsNone(predict(target, [donor]))


if __name__ == "__main__":
    unittest.main()
