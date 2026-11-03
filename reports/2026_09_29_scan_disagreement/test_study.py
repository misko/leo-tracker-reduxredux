import unittest

import numpy as np
from study import curvature, profile


class Quadratic:
    h = np.array([[4.0, 0.0, 1.0], [0.0, 3.0, 0.5], [1.0, 0.5, 2.0]])
    g = np.array([2.0, -1.0, 0.4])

    def evaluate(self, x):
        return dict(gradient=self.g - self.h @ x)


class Tests(unittest.TestCase):
    def test_quadratic_profile_and_newton_step(self):
        model = Quadratic()
        h, asym = curvature(model, np.zeros(3), 1.0)
        np.testing.assert_allclose(h, model.h, atol=1e-10)
        self.assertLess(asym, 1e-10)
        reduced, g = profile(h, model.g)
        np.testing.assert_allclose(
            np.linalg.solve(reduced, g), np.linalg.solve(model.h, model.g)[:2], atol=1e-10
        )

    def test_negative_timing_curvature_abstains(self):
        self.assertIsNone(profile(np.diag([1.0, 1.0, -1.0]), np.ones(3)))


if __name__ == "__main__":
    unittest.main()
