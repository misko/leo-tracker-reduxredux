import unittest

import numpy as np
from run import Weighted, response


class Quadratic:
    def __init__(self, precision, center):
        self.precision, self.center = np.array(precision), np.array(center)

    def evaluate(self, x, gradient=True):
        delta = np.array(x) - self.center
        return dict(score=-0.5 * delta @ self.precision @ delta, gradient=-self.precision @ delta)


class InfluenceTests(unittest.TestCase):
    def test_downweight_gradient_and_response_sign(self):
        full = Quadratic([[4.0, 1.0], [1.0, 3.0]], [0.0, 0.0])
        group = Quadratic([[1.0, 0.0], [0.0, 1.0]], [2.0, -1.0])
        x = np.zeros(2)
        direction = response(full.precision, group.evaluate(x)["gradient"], 1.0) / 1000
        fits = []
        for w in (0.999, 1.001):
            fits.append(
                np.linalg.solve(
                    full.precision + (w - 1) * group.precision,
                    (w - 1) * group.precision @ group.center,
                )
            )
        np.testing.assert_allclose((fits[1] - fits[0]) / 0.002, direction, rtol=1e-6)
        model = Weighted(full, group, 0.5)
        for i in range(2):
            p, m = x.copy(), x.copy()
            p[i] += 1e-5
            m[i] -= 1e-5
            numerical = (model.evaluate(p)["score"] - model.evaluate(m)["score"]) / 2e-5
            self.assertAlmostEqual(numerical, model.evaluate(x)["gradient"][i], places=8)


if __name__ == "__main__":
    unittest.main()
