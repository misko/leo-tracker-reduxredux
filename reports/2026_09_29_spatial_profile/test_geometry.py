import unittest

import numpy as np
from geometry import information, profile, relative_difference


class Tests(unittest.TestCase):
    def test_known_profile_and_displacement(self):
        # -logL = .5 * (2 E^2 + 5 N^2 + 7(t - 3E + N)^2).
        v = np.array([-3.0, 1.0, 1.0])
        h = np.diag([2.0, 5.0, 0.0]) + 7 * np.outer(v, v)
        raw, observed = information(lambda x: -h @ x, np.array([0.2, -0.1, 0.5]), [0.001] * 3)
        np.testing.assert_allclose(raw, h, atol=1e-10)
        spatial, response, values, vectors = profile(observed)
        np.testing.assert_allclose(spatial, np.diag([2, 5]), atol=1e-10)
        np.testing.assert_allclose(response, [[3, -1]], atol=1e-10)
        np.testing.assert_allclose(values, [2, 5], atol=1e-10)
        for direction in vectors.T:
            full = np.r_[direction, response @ direction]
            self.assertAlmostEqual(float(full @ h @ full), float(direction @ spatial @ direction))

    def test_unidentifiable_position(self):
        h = np.array([[1.0, 0.0, -1.0], [0.0, 2.0, 0.0], [-1.0, 0.0, 1.0]])
        _, _, values, _ = profile(h)
        np.testing.assert_array_equal(values, [0, 2])

    def test_nonpositive_timing(self):
        with self.assertRaises(ValueError):
            profile(np.diag([1.0, 1.0, 0.0]))

    def test_schur_via_independent_minimization(self):
        from scipy.optimize import minimize

        a = np.array(
            [[2.0, 0.0, 1.0, 2.0], [1.0, 3.0, 0.0, 1.0], [0.0, 2.0, 4.0, 1.0], [1.0, 0.0, 2.0, 3.0]]
        )
        h = a.T @ a + np.eye(4)
        spatial, _, _, _ = profile(h)
        point = np.array([0.5, -0.7])
        fit = minimize(
            lambda t: 0.5 * np.r_[point, t] @ h @ np.r_[point, t],
            [0.0, 0.0],
            jac=lambda t: (h @ np.r_[point, t])[2:],
            method="BFGS",
            options={"gtol": 1e-10},
        )
        self.assertAlmostEqual(float(fit.fun), 0.5 * float(point @ spatial @ point), places=10)

    def test_step_replay(self):
        h = np.array([[3.0, 1.0, 0.0], [1.0, 4.0, 1.0], [0.0, 1.0, 2.0]])
        _, a = information(lambda x: -h @ x, np.ones(3), np.full(3, 0.001))
        _, b = information(lambda x: -h @ x, np.ones(3), np.full(3, 0.0005))
        self.assertLess(relative_difference(a, b), 1e-10)


if __name__ == "__main__":
    unittest.main()
