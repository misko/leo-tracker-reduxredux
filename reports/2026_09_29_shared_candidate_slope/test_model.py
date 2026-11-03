import unittest

import numpy as np
from model import SharedSlope, marginal, quadrature
from scipy.special import logsumexp


class Prediction:
    def __init__(self, doc, config):
        pass

    def prediction(self, track, x):
        t = np.array(track["times_s"])
        return np.array([x[0] * t + x[1] * t * t + x[2] * t, 20 * t]), np.array([True, True])


class SharedTests(unittest.TestCase):
    def test_integrate_product_not_product_of_integrals(self):
        values = np.log(np.array([[0.9, 0.1], [0.9, 0.1]]))
        score, g = marginal(values, np.zeros((2, 2, 1)), np.log([0.5, 0.5]))
        self.assertAlmostEqual(np.exp(score), 0.41)
        self.assertNotAlmostEqual(np.exp(score), 0.25)
        np.testing.assert_array_equal(g, 0)
        _, w = quadrature(2.0, 128)
        self.assertAlmostEqual(logsumexp(w), 0.0)

    def test_zero_slope_limit_gradient_and_held_isolation(self):
        tracks = [
            dict(
                track_id=str(i),
                times_s=[0.0, 1.0, 3.0, 5.0],
                y=np.array([100.0, 115.0, 160.0, 190.0]) + i * 50,
                mask=np.array([True, True, True, False]),
            )
            for i in range(2)
        ]
        docs = [dict(session_id="s", tracks=tracks)]
        membership = {(0, 0): (1, 0), (0, 1): (1, 0)}
        model = SharedSlope(docs, {}, Prediction, membership, 2.0)
        x = np.array([12.0, 0.1, 0.2])
        out = model.evaluate(x, held=True)
        for i in range(3):
            p, m = x.copy(), x.copy()
            p[i] += 1e-4
            m[i] -= 1e-4
            numerical = (
                model.evaluate(p, False)["score"] - model.evaluate(m, False)["score"]
            ) / 2e-4
            self.assertAlmostEqual(numerical, out["gradient"][i], places=7)
        model.sigma = 0.0
        zero = model.evaluate(x, held=True)
        base = model.base.evaluate(x, held=True)
        self.assertAlmostEqual(zero["score"], base["score"], places=10)
        np.testing.assert_allclose(zero["gradient"], base["gradient"], atol=1e-10)
        self.assertAlmostEqual(
            zero["held_score"], sum(r["held_log_score"] for r in base["rows"]), places=10
        )
        tracks[0]["y"][-1] += 9999
        changed = SharedSlope(docs, {}, Prediction, membership, 2.0).evaluate(x, held=True)
        self.assertEqual(changed["score"], out["score"])
        np.testing.assert_array_equal(changed["gradient"], out["gradient"])
        self.assertNotEqual(changed["held_score"], out["held_score"])


if __name__ == "__main__":
    unittest.main()
