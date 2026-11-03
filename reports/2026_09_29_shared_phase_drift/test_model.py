import unittest

import numpy as np
from model import TS, learn, objective, prediction


class Tests(unittest.TestCase):
    def test_signed_recovery_gradient_and_held_isolation(self):
        mhz = np.array([-3.0, -1.0, 1.0, 3.0])
        f = np.array([130.0, 180.0, 250.0])
        drift = 17.0
        t = np.arange(300) * TS
        y = np.exp(2j * np.pi * t[None, :, None] * (f[:, None, None] - mhz[None, None, :] * drift))
        coarse = f + 10
        p = np.array([1.0, 2.0, 3.0, 4.0])
        _, g = objective(p, y, mhz, coarse)
        for i in range(4):
            plus, minus = p.copy(), p.copy()
            plus[i] += 1e-4
            minus[i] -= 1e-4
            fd = (objective(plus, y, mhz, coarse)[0] - objective(minus, y, mhz, coarse)[0]) / 2e-4
            self.assertAlmostEqual(g[i], fd, places=8)
        fit = learn(y, mhz, coarse)
        self.assertTrue(fit["qualified"])
        self.assertAlmostEqual(fit["drift_ppm"], drift, places=2)
        self.assertLess(prediction(y[0], mhz, coarse[0], fit["drift_ppm"])["nmse"], 1e-8)
        mutated = y.copy()
        mutated[:, 220:] *= 100j
        self.assertEqual(learn(mutated, mhz, coarse), fit)


if __name__ == "__main__":
    unittest.main()
