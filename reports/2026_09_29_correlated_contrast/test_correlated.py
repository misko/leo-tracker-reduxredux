"""Independent matrix, normalization, replay and geographic derivative checks."""
# ruff: noqa: I001 -- Load local model before importing its bootstrapped dependencies.

import copy
import math
import subprocess
import sys
import unittest
from fractions import Fraction
from pathlib import Path

import numpy as np
from correlated_trend import CorrelatedTrendPosition
from density import ContrastDensity
from contrast_position import contrast_density
from ds7_baseline_adapter import Stationary
from scipy.integrate import quad
from scipy.stats import multivariate_t
from test_contrast_position import fixture
from test_trend_mixture import PolynomialPrediction, toy as original_toy, trend_density
from trend_mixture import TrendMixturePosition


def toy():
    docs = original_toy()
    # Only candidate count is used in these no-cone polynomial tests.
    docs[0]["tracks"][0]["candidate_position_km"] = np.zeros((1, 1, 5, 3))
    return docs


def rational_density(values, base_shape, times, slope):
    """Assemble and solve the rank-one covariance without rounding its large sum."""
    t = [Fraction(float(v)) for v in times]
    a = [
        [Fraction(float(v)) + Fraction(slope) ** 2 * t[i] * t[j] for j, v in enumerate(row)]
        for i, row in enumerate(base_shape)
    ]
    b = [Fraction(float(v)) for v in values]
    determinant = Fraction(1)
    for i in range(len(b)):
        pivot = a[i][i]
        determinant *= pivot
        a[i] = [v / pivot for v in a[i]]
        b[i] /= pivot
        for j in range(len(b)):
            if j != i:
                multiplier = a[j][i]
                a[j] = [v - multiplier * w for v, w in zip(a[j], a[i], strict=True)]
                b[j] -= multiplier * b[i]
    q = sum(Fraction(float(v)) * w for v, w in zip(values, b, strict=True))
    n = len(b)
    return (
        math.lgamma((4 + n) / 2)
        - math.lgamma(2)
        - 0.5 * (n * math.log(4 * math.pi) + math.log(float(determinant)))
        - (4 + n) / 2 * math.log1p(float(q) / 4)
    )


class DensityTests(unittest.TestCase):
    def test_independent_matrix_all_anchors(self):
        times = np.array([0.0, 0.5, 2, 4, 7])
        y = np.array([12.0, -3, 8, 1, 9])
        for decay in (0, 10):
            kernel = (
                np.eye(5)
                if decay == 0
                else (0.8 * np.exp(-abs(times[:, None] - times[None, :]) / decay) + 0.2 * np.eye(5))
            )
            for slope in (0, 3, 2000):
                actual = ContrastDensity(times, decay, 2, slope)(y[None, :])[0][0]
                for anchor in range(5):
                    d = np.eye(5)[[i for i in range(5) if i != anchor]] - np.eye(5)[anchor]
                    shape = 4 * d @ kernel @ d.T + slope**2 * np.outer(d @ times, d @ times)
                    expected = rational_density(d @ y, 4 * d @ kernel @ d.T, d @ times, slope)
                    self.assertAlmostEqual(actual, expected, places=10)
                    if slope <= 3:
                        self.assertAlmostEqual(
                            actual, multivariate_t.logpdf(d @ y, shape=shape, df=4), places=10
                        )
                    order = [anchor] + [i for i in range(5) if i != anchor]
                    reordered = ContrastDensity(times[order], decay, 2, slope)(y[None, order])[0][0]
                    self.assertAlmostEqual(actual, reordered, places=10)

    def test_zero_decay_density_replay_and_translation(self):
        t = np.array([0.0, 1.0, 3.0, 7.0])
        y = np.array([[4.0, -6.0, 11.0, 2.0], [1.0, 3.0, -2.0, 7.0]])
        got = ContrastDensity(t, 0)(y)
        want = contrast_density(y)
        for a, b in zip(got, want, strict=True):
            np.testing.assert_allclose(a, b, atol=1e-12, rtol=1e-12)
        for decay in (0, 10):
            for slope in (0, 2000):
                a = ContrastDensity(t, decay, slope_scale=slope)(y)
                b = ContrastDensity(t + 1e6, decay, slope_scale=slope)(y + 1e6)
                for lhs, rhs in zip(a, b, strict=True):
                    np.testing.assert_allclose(lhs, rhs, atol=1e-12, rtol=1e-10)
        for row in y:
            self.assertAlmostEqual(
                ContrastDensity(t, 0, slope_scale=2000)(row[None, :])[0][0],
                trend_density(row, t),
                places=10,
            )

    def test_influence_against_finite_difference(self):
        y = np.array([[2.0, -4.0, 8.0, 3.0]])
        for slope in (0, 2000):
            density = ContrastDensity([0, 1, 2, 4], 10, slope_scale=slope)
            _, influence = density(y)
            for axis in range(4):
                step = np.eye(4)[axis][None, :] * 1e-3
                numeric = -(density(y + step)[0] - density(y - step)[0]) / 0.002
                self.assertAlmostEqual(influence[0, axis], numeric[0], places=9)
            self.assertAlmostEqual(float(influence.sum()), 0, places=14)

    def test_invalid_parameters_and_duplicate_times(self):
        for decay, noise, slope in ((-1, 100, 0), (10, 0, 0), (10, 100, -1), (math.nan, 100, 0)):
            with self.assertRaises(ValueError):
                ContrastDensity([0, 1], decay, noise, slope)
        density = ContrastDensity([0, 0, 0], 10, slope_scale=2000)
        self.assertTrue(np.isfinite(density(np.array([[1, 2, 3]]))[0]).all())


class ModelTests(unittest.TestCase):
    def test_fresh_process_imports_local_study_and_density(self):
        here = Path(__file__).resolve().parent
        code = (
            "import sys; from pathlib import Path; "
            f"here = Path({str(here)!r}); sys.path.insert(0,str(here)); "
            "import study; import correlated_trend; import density; "
            "assert study.HERE == here; "
            "assert Path(density.__file__).resolve().parent == here; "
            "assert Path(correlated_trend.__file__).resolve().parent == here"
        )
        subprocess.run([sys.executable, "-c", code], check=True, timeout=30)

    def test_zero_decay_replays_complete_mixture(self):
        docs, config = fixture()
        x = [0.3, -0.4, 0.17, 0.27]
        for q in (0, 0.2, 1):
            old = TrendMixturePosition(docs, config, Stationary, q).evaluate(x, held=True)
            new = CorrelatedTrendPosition(
                docs, config, Stationary, decay_s=0, background_probability=q
            ).evaluate(x, held=True)
            self.assertAlmostEqual(old["score"], new["score"], places=8)
            np.testing.assert_allclose(old["gradient"], new["gradient"], atol=1e-9)
            for a, b in zip(old["rows"], new["rows"], strict=True):
                self.assertAlmostEqual(a["held_log_score"], b["held_log_score"], places=8)
                self.assertAlmostEqual(
                    a["signal_responsibility"], b["signal_responsibility"], places=10
                )
                np.testing.assert_allclose(
                    np.asarray(a["weights_given_signal"]) * a["signal_responsibility"],
                    b["candidate_responsibilities"],
                    atol=1e-10,
                )

    def test_geographic_and_timing_gradients_with_cones(self):
        docs, config = fixture()
        x = np.array([0.3, -0.4, 0.17, 0.27])
        for width in (None, 40):
            model = CorrelatedTrendPosition(docs, config, Stationary, half_angle_deg=width)
            got = model.evaluate(x, held=True)
            for axis in range(4):
                for step in [0.001, 0.0005] if axis < 2 else [0.00005, 0.000025]:
                    delta = np.eye(4)[axis] * step
                    numeric = (
                        model.evaluate(x + delta, False)["score"]
                        - model.evaluate(x - delta, False)["score"]
                    ) / (2 * step)
                    self.assertLess(abs(numeric - got["gradient"][axis]), 2e-5)
            for row in got["rows"]:
                self.assertAlmostEqual(
                    sum(row["candidate_responsibilities"]) + row["background_responsibility"],
                    1,
                    places=12,
                )

    def test_held_isolation(self):
        docs, config = fixture()
        changed = copy.deepcopy(docs)
        for doc in changed:
            for track in doc["tracks"]:
                track["y"][~track["mask"]] += 10000
                track["candidate_position_km"][:, :, ~track["mask"], 1] += 1000
        x = [0.3, -0.4, 0.17, 0.27]
        a = CorrelatedTrendPosition(docs, config, Stationary, half_angle_deg=40).evaluate(
            x, held=True
        )
        b = CorrelatedTrendPosition(changed, config, Stationary, half_angle_deg=40).evaluate(
            x, held=True
        )
        self.assertEqual(a["score"], b["score"])
        np.testing.assert_array_equal(a["gradient"], b["gradient"])
        for r, s in zip(a["rows"], b["rows"], strict=True):
            self.assertEqual(r["candidate_responsibilities"], s["candidate_responsibilities"])
            self.assertNotEqual(r["held_log_score"], s["held_log_score"])

    def test_predictive_normalization(self):
        for q in (0, 0.2, 1):
            docs = toy()

            def predictive(y, docs=docs, q=q):
                docs[0]["tracks"][0]["y"][-1] = y
                model = CorrelatedTrendPosition(
                    docs,
                    {"timing_grid_s": [-5, 0, 5]},
                    PolynomialPrediction,
                    background_probability=q,
                )
                return math.exp(
                    model.evaluate([4, 280, 0], False, True)["rows"][0]["held_log_score"]
                )

            value, error = quad(predictive, -np.inf, np.inf, epsabs=1e-9, epsrel=1e-9)
            self.assertAlmostEqual(value, 1, places=7)
            self.assertLess(error, 1e-7)

    def test_background_zero_force_and_empty_bank_abstention(self):
        model = CorrelatedTrendPosition(
            toy(), {"timing_grid_s": [-5, 0, 5]}, PolynomialPrediction, background_probability=1
        )
        a, b = [model.evaluate(x, held=True) for x in ([4, 280, 0], [100, -100, 1])]
        self.assertEqual(a["score"], b["score"])
        np.testing.assert_array_equal(a["gradient"], np.zeros(3))

        class Invisible(PolynomialPrediction):
            def prediction(self, track, x):
                values, visible = super().prediction(track, x)
                return values, ~visible

        for q in (0, 0.2, 1):
            with self.assertRaisesRegex(ValueError, "outside conditional-bank domain"):
                CorrelatedTrendPosition(
                    toy(), {"timing_grid_s": [-5, 0, 5]}, Invisible, background_probability=q
                ).evaluate([0, 0, 0])


if __name__ == "__main__":
    unittest.main()
