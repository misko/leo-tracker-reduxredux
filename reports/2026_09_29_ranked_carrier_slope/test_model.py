import unittest

import numpy as np
from model import TS, errors, fit, objective


class CarrierSlopeTests(unittest.TestCase):
    def test_joint_signed_recovery(self):
        offsets = np.linspace(-0.82, 0.82, 8)
        gain = np.array([1 + 1j, 2 - 1j])[:, None, None]
        y = gain * np.exp(
            2j * np.pi * np.arange(300)[None, :, None] * TS * (-137 - offsets[None, None, :] * -42)
        )
        selected, _ = fit(y, offsets, -100)
        self.assertIsNotNone(selected)
        np.testing.assert_allclose(selected["parameters"], [-137, -42], atol=0.01)
        self.assertLess(max(errors(y, offsets, selected["parameters"])), 1e-8)

    def test_analytic_gradient(self):
        rng = np.random.default_rng(28)
        y = rng.normal(size=(3, 300, 8)) + 1j * rng.normal(size=(3, 300, 8))
        offsets = np.linspace(-0.82, 0.82, 8)
        p = np.array([0.12, -0.3])
        _, gradient = objective(p, y, offsets)
        for i in range(2):
            a, b = p.copy(), p.copy()
            a[i] += 1e-5
            b[i] -= 1e-5
            numerical = (objective(a, y, offsets)[0] - objective(b, y, offsets)[0]) / 2e-5
            self.assertAlmostEqual(numerical, gradient[i], places=8)

    def test_held_values_cannot_change_fit(self):
        rng = np.random.default_rng(8)
        y = rng.normal(size=(2, 300, 4)) + 1j * rng.normal(size=(2, 300, 4))
        z = y.copy()
        z[:, 220:] *= 1e8
        offsets = np.linspace(-0.8, 0.8, 4)
        self.assertEqual(fit(y, offsets, 0), fit(z, offsets, 0))


if __name__ == "__main__":
    unittest.main()
