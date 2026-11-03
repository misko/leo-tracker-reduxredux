import math
import sys
import unittest
from pathlib import Path

import numpy as np
from scipy.integrate import quad
from scipy.optimize import brentq

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE), str(ROOT / "tools")]

import ds7_fast_baseline_adapter as fast_baseline  # noqa: E402
from model import (  # noqa: E402
    RobustIID,
    VARIANTS,
    _offset_gradient,
    _offset_gradients,
    _offset_loss,
    fit_stationary_offsets,
    profile_likelihood,
    resolve_variant,
    student_t_log_density,
)


class PolynomialPrediction:
    def __init__(self, document, config):
        del document, config

    def coordinates(self, x):
        return float(x[1]), float(x[0])

    def prediction(self, track, x):
        times = np.asarray(track["times_s"], dtype=float)
        prediction = np.stack(
            [
                x[0] * times + x[1] * times**2 + x[2] * (1.0 + 0.2 * times),
                -0.3 * x[0] * times + 0.5 * x[1] * times**2 + x[2] * (1.0 - times),
            ]
        )
        return prediction, np.array([True, True])


class RobustLikelihoodTests(unittest.TestCase):
    def test_vectorized_bracketing_gradient_is_scalar_equivalent(self):
        values = np.array([-1200.0, -87.5, 12.0, 405.0, 990.0])
        nodes = np.linspace(-1400.0, 1200.0, 127)
        for name in ("scale50", "scale200", "df2", "df8", "baseline"):
            variant = resolve_variant(name)
            scalar = np.array([_offset_gradient(node, values, variant) for node in nodes])
            vector = _offset_gradients(nodes, values, variant)
            np.testing.assert_array_equal(vector, scalar)

    def test_variants_are_bounded_and_density_is_normalized(self):
        expected = {
            "scale50": (4.0, 50.0),
            "scale200": (4.0, 200.0),
            "df2": (2.0, 100.0),
            "df8": (8.0, 100.0),
        }
        self.assertEqual(
            {name: (VARIANTS[name].df, VARIANTS[name].scale_hz) for name in expected},
            expected,
        )
        for name in expected:
            variant = resolve_variant(name)
            integral, error = quad(
                lambda value: math.exp(
                    float(student_t_log_density(value, variant.df, variant.scale_hz))
                ),
                -np.inf,
                np.inf,
            )
            self.assertAlmostEqual(integral, 1.0, places=10, msg=f"{name}: {error}")

    def test_df4_scale100_profile_matches_frozen_fast_baseline(self):
        values = np.array(
            [
                [-410.0, -92.0, 1.0, 87.0, 530.0],
                [200.0, 210.0, 190.0, 220.0, -900.0],
                [-1000.0, -980.0, 970.0, 1030.0, 1010.0],
            ]
        )
        ours, audits = fit_stationary_offsets(values, "baseline")
        frozen, frozen_audits = fast_baseline.fit_stationary_offsets(values, sigma=100.0)
        np.testing.assert_allclose(ours, frozen, rtol=0.0, atol=2e-8)
        self.assertTrue(all(audit["converged"] for audit in audits))
        self.assertTrue(all(audit["converged"] for audit in frozen_audits))

        residual = np.c_[values, values[:, :2] + 17.0]
        mask = np.array([True] * 5 + [False] * 2)
        score, _, offsets, _ = profile_likelihood(residual, mask, "baseline")
        frozen_score, _, _, frozen_offsets = fast_baseline.profile(residual, mask)
        np.testing.assert_allclose(offsets, frozen_offsets, rtol=0.0, atol=2e-8)
        np.testing.assert_allclose(score, frozen_score, rtol=0.0, atol=2e-10)

    def test_profiler_selects_stationary_solution_across_multiple_modes(self):
        # Two tight, distant clusters yield two positive-curvature Student-t
        # offset modes.  A one-start local optimizer can select either one.
        values = np.array([[-1030.0, -1000.0, -970.0, 960.0, 990.0, 1020.0, 1050.0]])
        for name in ("scale50", "df2", "baseline"):
            variant = resolve_variant(name)
            offsets, audits = fit_stationary_offsets(values, variant)
            self.assertGreaterEqual(audits[0]["roots"], 2, name)
            self.assertLess(abs(_offset_gradient(offsets[0], values[0], variant)), 1e-7)

            # Independently enumerate stationary roots on a dense grid and
            # check the profiler selected the global stationary minimum.
            grid = np.linspace(values.min(), values.max(), 40001)
            gradient = np.array([_offset_gradient(v, values[0], variant) for v in grid])
            roots = [
                brentq(
                    lambda offset: _offset_gradient(offset, values[0], variant),
                    grid[index],
                    grid[index + 1],
                )
                for index in np.flatnonzero((gradient[:-1] < 0.0) & (gradient[1:] > 0.0))
            ]
            expected = min(_offset_loss(root, values[0], variant) for root in roots)
            self.assertAlmostEqual(
                _offset_loss(offsets[0], values[0], variant), expected, places=10
            )

    def test_envelope_gradient_matches_finite_difference_and_held_rows_are_isolated(self):
        track = {
            "track_id": "synthetic",
            "times_s": [-2.0, -0.5, 0.7, 2.2, 3.1],
            "y": np.array([80.0, 92.0, 101.0, 130.0, -9000.0]),
            "mask": np.array([True, True, True, True, False]),
            "catalogue_size": 7,
        }
        documents = [{"tracks": [track]}]
        x = np.array([3.2, -0.7, 0.15])
        for name in ("scale50", "scale200", "df2", "df8"):
            model = RobustIID(documents, {}, name, prediction_factory=PolynomialPrediction)
            outcome = model.evaluate(x)
            for axis, step in enumerate((1e-5, 1e-5, 1e-6)):
                delta = np.eye(3)[axis] * step
                numerical = (
                    model.evaluate(x + delta, gradient=False)["score"]
                    - model.evaluate(x - delta, gradient=False)["score"]
                ) / (2.0 * step)
                self.assertAlmostEqual(
                    numerical, outcome["gradient"][axis], delta=3e-5, msg=f"{name} axis {axis}"
                )

            original = model.evaluate(x)
            track["y"][-1] += 1e6
            changed = model.evaluate(x)
            self.assertEqual(original["score"], changed["score"])
            np.testing.assert_array_equal(original["gradient"], changed["gradient"])
            track["y"][-1] -= 1e6

    def test_multiple_documents_share_position_but_keep_separate_timing_gradients(self):
        def make_track(shift):
            return {
                "track_id": f"synthetic-{shift}",
                "times_s": [-1.5, -0.2, 0.8, 2.0],
                "y": np.array([40.0, 61.0, 73.0, 95.0]) + shift,
                "mask": np.ones(4, dtype=bool),
                "catalogue_size": 2,
            }

        documents = [{"tracks": [make_track(0.0)]}, {"tracks": [make_track(23.0)]}]
        model = RobustIID(documents, {}, "df8", prediction_factory=PolynomialPrediction)
        x = np.array([1.4, -0.3, 0.2, -0.4])
        outcome = model.evaluate(x)
        for axis, step in enumerate((1e-5, 1e-5, 1e-6, 1e-6)):
            delta = np.eye(4)[axis] * step
            numerical = (
                model.evaluate(x + delta, gradient=False)["score"]
                - model.evaluate(x - delta, gradient=False)["score"]
            ) / (2.0 * step)
            self.assertAlmostEqual(numerical, outcome["gradient"][axis], delta=3e-5)


if __name__ == "__main__":
    unittest.main()
