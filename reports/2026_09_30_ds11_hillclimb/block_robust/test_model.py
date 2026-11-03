import math
import sys
import unittest
from pathlib import Path

import numpy as np
from scipy.optimize import brentq

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE), str(ROOT / "tools")]

import ds7_fast_baseline_adapter as fast_baseline  # noqa: E402
from ds789_correlated_residual import multivariate_t  # noqa: E402
from ds789_covariance_position import profile_offsets  # noqa: E402
from model import (  # noqa: E402
    BlockRobust,
    VARIANTS,
    _offset_gradient,
    _offset_loss,
    block_log_density,
    fit_stationary_offsets,
    make_block_layout,
    profile_likelihood,
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


class BlockRobustTests(unittest.TestCase):
    def test_variants_and_exact_training_only_grouping(self):
        self.assertEqual(
            {name: variant.block_seconds for name, variant in VARIANTS.items()},
            {"block1": 1.0, "block3": 3.0, "block10": 10.0},
        )
        times = np.array([10.0, 10.9, 11.0, 12.99, 13.0, 1000.0])
        mask = np.array([True, True, True, True, True, False])
        layout = make_block_layout(times, mask, 3.0)
        np.testing.assert_array_equal(layout.ids, [0, 0, 0, 0, 1])
        np.testing.assert_array_equal(layout.sizes, [4, 1])
        self.assertEqual(layout.anchor_s, 10.0)

    def test_one_observation_blocks_reproduce_original_iid_profile(self):
        values = np.array(
            [
                [-410.0, -92.0, 1.0, 87.0, 530.0],
                [200.0, 210.0, 190.0, 220.0, -900.0],
                [-1000.0, -980.0, 970.0, 1030.0, 1010.0],
            ]
        )
        residual = np.c_[values, values[:, :2] + 17.0]
        mask = np.array([True] * 5 + [False] * 2)
        times = np.arange(7, dtype=float) * 2.0
        score, influence, offsets, audits = profile_likelihood(residual, mask, times, 1.0)
        expected, _, frozen_audits, frozen_offsets = fast_baseline.profile(residual, mask)
        np.testing.assert_allclose(offsets, frozen_offsets, rtol=0.0, atol=3e-8)
        np.testing.assert_allclose(score, expected, rtol=0.0, atol=3e-10)
        centered = residual[:, mask] - offsets[:, None]
        expected_influence = 5.0 * centered / (4.0 * 100.0**2 + centered**2)
        np.testing.assert_allclose(influence, expected_influence, rtol=0.0, atol=2e-14)
        self.assertTrue(all(audit["converged"] for audit in audits + frozen_audits))

    def test_one_block_reproduces_shared_scale_covariance_score_and_profile(self):
        values = np.array(
            [
                [80.0, 92.0, 101.0, 130.0, 117.0],
                [-130.0, -95.0, -87.0, -102.0, -75.0],
                [900.0, 920.0, 875.0, 940.0, 910.0],
            ]
        )
        mask = np.ones(values.shape[1], dtype=bool)
        times = np.arange(values.shape[1], dtype=float)
        score, influence, offsets, _ = profile_likelihood(values, mask, times, math.inf)

        precision = np.eye(values.shape[1]) / 100.0**2
        expected_offsets, q, expected_influence, _ = profile_offsets(values, precision)
        logdet = values.shape[1] * math.log(100.0**2)
        expected_score = multivariate_t(q, logdet, values.shape[1], 1.0)
        expected_score -= 0.5 * expected_offsets**2 / 1e12
        np.testing.assert_allclose(offsets, expected_offsets, rtol=0.0, atol=2e-8)
        np.testing.assert_allclose(score, expected_score, rtol=0.0, atol=2e-11)
        np.testing.assert_allclose(influence, expected_influence, rtol=0.0, atol=2e-13)

        layout = make_block_layout(times, mask, math.inf)
        np.testing.assert_allclose(
            block_log_density(values - offsets[:, None], layout),
            expected_score + 0.5 * expected_offsets**2 / 1e12,
            rtol=0.0,
            atol=2e-11,
        )

    def test_profiler_selects_best_located_mode_across_blocks(self):
        values = np.array([[-1030.0, -1000.0, -970.0, 960.0, 990.0, 1020.0, 1050.0]])
        times = np.array([0.0, 0.1, 0.2, 2.0, 2.1, 2.2, 2.3])
        layout = make_block_layout(times, np.ones(7, dtype=bool), 1.0)
        offsets, audits = fit_stationary_offsets(values, layout)
        self.assertGreaterEqual(audits[0]["roots"], 2)
        self.assertLess(abs(_offset_gradient(offsets[0], values[0], layout)), 1e-7)

        grid = np.linspace(values.min(), values.max(), 50001)
        gradient = np.array([_offset_gradient(value, values[0], layout) for value in grid])
        roots = [
            brentq(
                lambda offset: _offset_gradient(offset, values[0], layout),
                grid[index],
                grid[index + 1],
            )
            for index in np.flatnonzero((gradient[:-1] < 0.0) & (gradient[1:] > 0.0))
        ]
        expected = min(_offset_loss(root, values[0], layout) for root in roots)
        self.assertAlmostEqual(_offset_loss(offsets[0], values[0], layout), expected, places=10)

    def test_envelope_gradient_and_held_rows_are_independent(self):
        track = {
            "track_id": "synthetic",
            "times_s": np.array([-2.0, -0.5, 0.7, 2.2, 3.1, 3.9]),
            "y": np.array([80.0, 92.0, 101.0, 130.0, -9000.0, 7000.0]),
            "mask": np.array([True, True, True, True, False, False]),
            "catalogue_size": 7,
        }
        documents = [{"tracks": [track]}]
        x = np.array([3.2, -0.7, 0.15])
        for name in VARIANTS:
            model = BlockRobust(documents, {}, name, prediction_factory=PolynomialPrediction)
            outcome = model.evaluate(x)
            for axis, step in enumerate((1e-5, 1e-5, 1e-6)):
                delta = np.eye(3)[axis] * step
                numerical = (
                    model.evaluate(x + delta, gradient=False)["score"]
                    - model.evaluate(x - delta, gradient=False)["score"]
                ) / (2.0 * step)
                self.assertAlmostEqual(
                    numerical,
                    outcome["gradient"][axis],
                    delta=4e-5,
                    msg=f"{name} axis {axis}",
                )

            original = model.evaluate(x)
            held_y = track["y"][~track["mask"]].copy()
            held_t = track["times_s"][~track["mask"]].copy()
            track["y"][~track["mask"]] += np.array([1e6, -2e6])
            track["times_s"][~track["mask"]] += np.array([100.0, 200.0])
            changed = model.evaluate(x)
            self.assertEqual(original["score"], changed["score"])
            np.testing.assert_array_equal(original["gradient"], changed["gradient"])
            track["y"][~track["mask"]] = held_y
            track["times_s"][~track["mask"]] = held_t


if __name__ == "__main__":
    unittest.main()
