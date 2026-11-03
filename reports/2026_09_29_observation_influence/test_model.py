import unittest

import numpy as np
from model import terms


class InfluenceTests(unittest.TestCase):
    def setUp(self):
        rng = np.random.default_rng(109)
        self.y = rng.normal(0, 100, 7)
        self.t = np.arange(7)
        self.p = rng.normal(0, 50, (3, 7))
        self.d = rng.normal(0, 20, (3, 7, 3))

    def test_cross_derivative_includes_mixture_weights(self):
        _, _, cross = terms(self.y, self.t, self.p, self.d)
        numerical = []
        for i in range(len(self.y)):
            a, b = self.y.copy(), self.y.copy()
            a[i] += 0.001
            b[i] -= 0.001
            numerical.append(
                (terms(a, self.t, self.p, self.d)[1] - terms(b, self.t, self.p, self.d)[1]) / 0.002
            )
        np.testing.assert_allclose(cross, np.array(numerical).T, atol=1e-10, rtol=1e-6)

    def test_prediction_gradient(self):
        _, gradient, _ = terms(self.y, self.t, self.p, self.d)
        for i in range(3):
            a = terms(self.y, self.t, self.p + 0.0001 * self.d[:, :, i], self.d)[0]
            b = terms(self.y, self.t, self.p - 0.0001 * self.d[:, :, i], self.d)[0]
            self.assertAlmostEqual((a - b) / 0.0002, gradient[i], places=7)

    def test_constant_frequency_has_no_position_response(self):
        _, _, cross = terms(self.y, self.t, self.p, self.d)
        np.testing.assert_allclose(cross.sum(axis=1), 0, atol=1e-12)


if __name__ == "__main__":
    unittest.main()
