import copy
import unittest

import numpy as np
from estimator import TS, errors, fit
from prepare import select_track


class WaveformTests(unittest.TestCase):
    def test_frequency_recovery(self):
        t = np.arange(300) * TS
        gain = np.array([[1 + 2j, 2 - 1j], [3j, 1j]])
        y = gain[:, None, :] * np.exp(2j * np.pi * 137 * t)[None, :, None]
        f = fit(y, np.arange(20, 220))
        self.assertAlmostEqual(f, 137, places=3)
        self.assertLess(max(errors(y, f)), 1e-10)

    def test_held_isolation(self):
        rng = np.random.default_rng(51)
        y = rng.normal(size=(2, 300, 3)) + 1j * rng.normal(size=(2, 300, 3))
        z = y.copy()
        z[:, 220:] *= 1e5
        self.assertEqual(fit(y, np.arange(20, 220)), fit(z, np.arange(20, 220)))

    def test_selection_ignores_held_times(self):
        tracks = [
            dict(
                receiver_id=0,
                track_id="a",
                training_mask=[True, False, True],
                times_s=[3, 4, 5],
                visits=[1, 2, 3],
            ),
            dict(
                receiver_id=0,
                track_id="b",
                training_mask=[True, False, True],
                times_s=[1, 2, 6],
                visits=[4, 5, 6],
            ),
        ]
        self.assertEqual(select_track(tracks, 0)["track"]["track_id"], "b")
        changed = copy.deepcopy(tracks)
        changed[0]["times_s"][1] = -1e9
        self.assertEqual(select_track(changed, 0)["track"]["track_id"], "b")


if __name__ == "__main__":
    unittest.main()
