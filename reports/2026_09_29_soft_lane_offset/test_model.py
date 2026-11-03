import unittest

import numpy as np
from model import PERIOD, SoftOffsetPosition, contrast_density, offset_density
from scipy.integrate import quad
from scipy.stats import t


class FakePrediction:
    def __init__(self, doc, config):
        pass

    def prediction(self, track, x):
        times = np.asarray(track["times_s"])
        return np.array([x[0] * times + x[1] * times**2 + 3 * x[2] * times]), np.array([True])


class OffsetTests(unittest.TestCase):
    def test_held_values_do_not_change_training_fit(self):
        track = dict(
            track_id="t",
            y=np.array([100.0, 120.0, 140.0, 500.0]),
            mask=np.array([True, True, True, False]),
            times_s=[0.0, 1.0, 2.0, 3.0],
            receiver_id="RX0",
            rf_hz=11.2e9,
        )
        doc = dict(session_id="s", tracks=[track])
        model = SoftOffsetPosition([doc], {}, FakePrediction, 0.2)
        x = np.array([20.0, 0.1, 0.2, 0.1])
        original = model.evaluate(x, held=True)
        track["y"][-1] += 10000
        changed = SoftOffsetPosition([doc], {}, FakePrediction, 0.2).evaluate(x, held=True)
        self.assertEqual(original["score"], changed["score"])
        np.testing.assert_array_equal(original["gradient"], changed["gradient"])
        self.assertNotEqual(
            original["rows"][0]["held_log_score"], changed["rows"][0]["held_log_score"]
        )
        for i in range(4):
            p, m = x.copy(), x.copy()
            p[i] += 1e-4
            m[i] -= 1e-4
            numerical = (
                model.evaluate(p, gradient=False)["score"]
                - model.evaluate(m, gradient=False)["score"]
            ) / 2e-4
            self.assertAlmostEqual(numerical, original["gradient"][i], places=6)

    def test_normalization_and_uniform_limit(self):
        k = 2 * np.pi / PERIOD
        rho = np.exp(-k * 3000)
        value = quad(
            lambda d: (1 - rho * rho) / ((1 - rho) ** 2 + 2 * rho * (1 - np.cos(k * d))) / PERIOD,
            -PERIOD / 2,
            PERIOD / 2,
            epsabs=1e-10,
        )[0]
        self.assertAlmostEqual(value, 1, places=10)
        r = np.array([[1200.0, 1000.0, 1050.0, 900.0]])
        a, b, c = offset_density(r, 1.03, 900, np.inf)
        d, e = contrast_density(r)
        np.testing.assert_allclose(a, d)
        np.testing.assert_allclose(b, e)
        np.testing.assert_array_equal(c, 0)

    def test_derivatives_alias_and_integral(self):
        r = np.array([[1200.0, 1000.0, 1050.0, 900.0], [-3000.0, -3200.0, -2900.0, -3100.0]])
        a, influence, g = offset_density(r, 1.03, 900, 3000)
        for i in range(r.shape[1]):
            plus, minus = r.copy(), r.copy()
            plus[:, i] += 0.01
            minus[:, i] -= 0.01
            numerical = (
                offset_density(plus, 1.03, 900, 3000)[0] - offset_density(minus, 1.03, 900, 3000)[0]
            ) / 0.02
            np.testing.assert_allclose(numerical, -influence[:, i], atol=1e-9)
        numerical = (
            offset_density(r, 1.03, 900.01, 3000)[0] - offset_density(r, 1.03, 899.99, 3000)[0]
        ) / 0.02
        np.testing.assert_allclose(numerical * 1000, g, atol=1e-8)
        np.testing.assert_allclose(
            offset_density(r + PERIOD / 1.03, 1.03, 900, 3000)[0], a, atol=1e-10
        )
        n = r.shape[1]
        scale = 1.03 * np.sqrt(
            (40000 + np.sum((r - r.mean(axis=1, keepdims=True)) ** 2, axis=1)) / (n * (n + 3))
        )
        k, rho = 2 * np.pi / PERIOD, np.exp(-2 * np.pi * 3000 / PERIOD)
        for i in range(len(r)):
            delta = 1.03 * r[i].mean() - 900
            value = quad(
                lambda q, delta=delta, i=i: (
                    t.pdf(q, n + 3)
                    * (1 - rho * rho)
                    / ((1 - rho) ** 2 + 2 * rho * (1 - np.cos(k * (delta - scale[i] * q))))
                ),
                -np.inf,
                np.inf,
                epsabs=1e-10,
            )[0]
            self.assertLess(abs(a[i] - contrast_density(r)[0][i] - np.log(value)), 1e-5)


if __name__ == "__main__":
    unittest.main()
