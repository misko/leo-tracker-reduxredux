import copy
import unittest

import numpy as np
from fit import centered, fit


def row(beta=0.2):
    t = np.arange(20.0)
    return dict(
        unit_id="DS7_early_8",
        residual=(800 + beta * t * 100).tolist(),
        delta=(200 + t * 100).tolist(),
        mask=(t % 2 == 0).tolist(),
    )


class RevisionFitTests(unittest.TestCase):
    def test_coefficient_recovery(self):
        self.assertAlmostEqual(fit([row()])["beta"], 0.2, places=6)
        self.assertEqual(fit([row(2)])["beta"], 1.0)

    def test_held_isolation(self):
        original = row()
        changed = copy.deepcopy(original)
        changed["residual"][1::2] = [1e8] * 10
        changed["delta"][1::2] = [-1e8] * 10
        self.assertEqual(fit([original]), fit([changed]))

    def test_centering_removes_constants(self):
        r = row()
        e, d, m = centered(r)
        self.assertAlmostEqual(e[m].mean(), 0)
        self.assertAlmostEqual(d[m].mean(), 0)
        r["residual"] = (np.asarray(r["residual"]) + 7000).tolist()
        np.testing.assert_allclose(centered(r)[0], e)


if __name__ == "__main__":
    unittest.main()
