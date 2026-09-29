"""Independent density, prediction and geographic-force tests."""

import copy
import math
import sys
import unittest
from fractions import Fraction
from pathlib import Path

import numpy as np
from scipy.integrate import quad
from scipy.stats import multivariate_t

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "2026_09_29_frequency_contrast"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from contrast_position import ContrastPosition, contrast_density  # noqa: E402
from ds7_baseline_adapter import Stationary  # noqa: E402
from test_contrast_position import fixture  # noqa: E402
from trend_mixture import TrendMixturePosition, trend_density  # noqa: E402


def exact_matrix_density(y, shape):
    """Exact rational elimination avoids an ill-conditioned eigenvalue oracle."""
    a = [[Fraction(float(v)) for v in row] for row in shape]
    b = [Fraction(float(v)) for v in y]
    determinant = Fraction(1)
    for i in range(len(y)):
        pivot = a[i][i]
        determinant *= pivot
        a[i] = [v / pivot for v in a[i]]
        b[i] /= pivot
        for j in range(len(y)):
            if i == j:
                continue
            multiplier = a[j][i]
            a[j] = [v - multiplier * w for v, w in zip(a[j], a[i], strict=True)]
            b[j] -= multiplier * b[i]
    q = sum(Fraction(float(v)) * w for v, w in zip(y, b, strict=True))
    n = len(y)
    return (
        math.lgamma((4 + n) / 2)
        - math.lgamma(2)
        - 0.5 * (n * math.log(4 * math.pi) + math.log(float(determinant)))
        - (4 + n) / 2 * math.log1p(float(q) / 4)
    )


class PolynomialPrediction:
    def __init__(self, doc, config):
        pass

    def prediction(self, track, x):
        t = np.asarray(track["times_s"])
        return (x[0] * t**2 + x[1] * t)[None, :], np.ones(1, dtype=bool)

    def coordinates(self, x):
        return x[:2]


def toy():
    t = np.arange(5.0)
    return [
        {
            "session_id": "toy",
            "tracks": [
                {
                    "track_id": "toy",
                    "times_s": t,
                    "y": 300 * t,
                    "mask": np.array([True, True, True, True, False]),
                    "catalogue_size": 100,
                }
            ],
        }
    ]


class DensityTests(unittest.TestCase):
    def test_matrix_all_anchors_and_translations(self):
        y = np.array([12.0, -3, 8, 1, 9])
        t = np.array([0.0, 0.5, 2, 4, 7])
        for slope in (0, 3, 2000):
            actual = trend_density(y, t, 2, slope)
            for anchor in range(len(y)):
                d = (
                    np.eye(len(y))[[i for i in range(len(y)) if i != anchor]]
                    - np.eye(len(y))[anchor]
                )
                shape = 4 * d @ d.T + slope**2 * np.outer(d @ t, d @ t)
                expected = exact_matrix_density(d @ y, shape)
                self.assertAlmostEqual(actual, expected, places=11)
                if slope <= 3:
                    self.assertAlmostEqual(
                        actual, multivariate_t.logpdf(d @ y, shape=shape, df=4), places=10
                    )
            self.assertAlmostEqual(actual, trend_density(y + 1e6, t + 1e6, 2, slope), places=11)
        self.assertAlmostEqual(
            trend_density(y, t, 2, 0), contrast_density(y[None, :], 2)[0], places=11
        )

    def test_density_and_mixture_predictive_normalization(self):
        value, error = quad(
            lambda y: math.exp(trend_density([0, y], [0, 1], 2, 3)),
            -np.inf,
            np.inf,
            epsabs=1e-10,
            epsrel=1e-10,
        )
        self.assertAlmostEqual(value, 1, places=9)
        self.assertLess(error, 1e-8)
        for probability in (0, 0.2, 1):
            docs = toy()

            def predictive(y, docs=docs, probability=probability):
                docs[0]["tracks"][0]["y"][-1] = y
                model = TrendMixturePosition(docs, {}, PolynomialPrediction, probability)
                return math.exp(
                    model.evaluate([4, 280, 0], False, True)["rows"][0]["held_log_score"]
                )

            value, error = quad(predictive, -np.inf, np.inf, epsabs=1e-9, epsrel=1e-9)
            self.assertAlmostEqual(value, 1, places=7)
            self.assertLess(error, 1e-7)


class ModelTests(unittest.TestCase):
    def test_zero_probability_matches_conditional_bank_control(self):
        docs, config = fixture()
        x = [0.3, -0.4, 0.17, 0.27]
        old = ContrastPosition(docs, config, Stationary).evaluate(x, held=True)
        new = TrendMixturePosition(docs, config, Stationary, 0).evaluate(x, held=True)
        correction = sum(
            math.log(t["catalogue_size"]) - math.log(r["visible_candidates"])
            for t, r in zip([t for d in docs for t in d["tracks"]], new["rows"], strict=True)
        )
        self.assertAlmostEqual(new["score"] - old["score"], correction, places=10)
        np.testing.assert_allclose(new["gradient"], old["gradient"], atol=1e-12)
        for a, b in zip(old["rows"], new["rows"], strict=True):
            self.assertAlmostEqual(a["held_log_score"], b["held_log_score"], places=10)
            np.testing.assert_array_equal(a["weights"], b["weights_given_signal"])
            self.assertEqual(b["signal_responsibility"], 1)

    def test_unit_background_has_no_geographic_force(self):
        docs, config = fixture()
        model = TrendMixturePosition(docs, config, Stationary, 1)
        a = model.evaluate([0.3, -0.4, 0.17, 0.27], held=True)
        b = model.evaluate([2, -2, 1.1, -1.1], held=True)
        self.assertEqual(a["score"], b["score"])
        np.testing.assert_array_equal(a["gradient"], np.zeros(4))
        for r, s in zip(a["rows"], b["rows"], strict=True):
            self.assertEqual(r["held_log_score"], s["held_log_score"])
            self.assertEqual(r["signal_responsibility"], 0)

    def test_unexplained_track_force_is_reduced(self):
        docs = toy()
        x = [1000, -200, 0]
        a = TrendMixturePosition(docs, {}, PolynomialPrediction, 0).evaluate(x, held=True)
        b = TrendMixturePosition(docs, {}, PolynomialPrediction, 0.2).evaluate(x, held=True)
        rho = b["rows"][0]["signal_responsibility"]
        self.assertLess(rho, 0.001)
        self.assertGreater(np.linalg.norm(a["gradient"]), 0.001)
        np.testing.assert_allclose(b["gradient"], rho * a["gradient"], atol=1e-14)

    def test_every_geographic_and_timing_derivative(self):
        docs, config = fixture()
        model = TrendMixturePosition(docs, config, Stationary, 0.2)
        x = np.array([0.3, -0.4, 0.17, 0.27])
        a = model.evaluate(x)
        for axis in range(len(x)):
            step = 0.001 if axis < 2 else 0.00005
            delta = np.eye(len(x))[axis] * step
            finite = (
                model.evaluate(x + delta, False)["score"]
                - model.evaluate(x - delta, False)["score"]
            ) / (2 * step)
            self.assertLess(abs(finite - a["gradient"][axis]), 2e-5)

    def test_held_isolation_with_rebuilt_background(self):
        docs, config = fixture()
        changed = copy.deepcopy(docs)
        for doc in changed:
            for track in doc["tracks"]:
                track["y"][~track["mask"]] += 10000
                track["candidate_position_km"][:, :, ~track["mask"], 1] += 1000
        x = [0.3, -0.4, 0.17, 0.27]
        a = TrendMixturePosition(docs, config, Stationary, 0.2).evaluate(x, held=True)
        b = TrendMixturePosition(changed, config, Stationary, 0.2).evaluate(x, held=True)
        self.assertEqual(a["score"], b["score"])
        np.testing.assert_array_equal(a["gradient"], b["gradient"])
        for r, s in zip(a["rows"], b["rows"], strict=True):
            self.assertEqual(r["signal_responsibility"], s["signal_responsibility"])
            self.assertNotEqual(r["held_log_score"], s["held_log_score"])

    def test_empty_visible_bank_abstains_in_every_arm(self):
        class Invisible(PolynomialPrediction):
            def prediction(self, track, x):
                prediction, visible = super().prediction(track, x)
                return prediction, ~visible

        for probability in (0, 0.2, 1):
            with self.assertRaisesRegex(ValueError, "outside conditional-bank domain"):
                TrendMixturePosition(toy(), {}, Invisible, probability).evaluate([0, 0, 0])


if __name__ == "__main__":
    unittest.main()
