"""Checks against an independently constructed direct bounded fit."""

import unittest

import numpy as np
from scipy.optimize import lsq_linear

import consensus as pilot


def fixture():
    rng = np.random.default_rng(1909)
    n, samples = 18, pilot.cold.SAMPLES
    ids = np.repeat(np.arange(1000, 1009), [3, 1, 2, 1, 4, 1, 1, 2, 3])
    group = rng.integers(0, 4, n)
    rf = rng.uniform(-.7, .7, n)
    times = rng.uniform(0, 250, (n, samples))
    gradients = rng.uniform(-60, 80, (n, samples, 2))
    rate = rng.uniform(1000, 6000, (n, samples))
    phase = rng.normal(0, .15, size=9)
    bias = np.array([-300., 700., -150., 30.])
    positions = np.array([16., -9.])
    frequency = gradients @ positions + rate * phase[ids - 1000, None] + bias[group, None]
    frequency += 180. * rf[:, None] + rng.normal(0, 50, (n, samples))
    frequency[::3] += pilot.cold.PERIOD
    raw = np.concatenate((frequency[:, :, None], gradients, rate[:, :, None]), axis=2)
    return pilot.Tracks(group, rf, times, raw, ids), bias


def direct_fit(tracks, bias, fitted):
    """Explicit dense columns and bounded least squares with no elimination."""
    n, samples = tracks.raw.shape[:2]
    unique, family, counts = np.unique(tracks.ids, return_counts=True, return_inverse=True)
    n_global = 11 if fitted else 10
    columns = n_global + len(unique)
    design = np.zeros((n, samples, columns))
    design[:, :, :2] = tracks.raw[:, :, 1:3] * pilot.HALF_WIDTH
    for row in range(n):
        lane = tracks.group[row]
        design[row, :, 2 + lane] = 32000.
        design[row, :, 6 + lane] = 750. * (tracks.times[row] - 150.) / 150.
        design[row, :, n_global + family[row]] = tracks.raw[row, :, 3] * pilot.cold.PHASE_SD_S
    if fitted:
        design[:, :, 10] = 200000. * tracks.rf[:, None]
    y = tracks.raw[:, :, 0] - bias[tracks.group, None]
    y = y - np.rint(y.mean(axis=1) / pilot.cold.PERIOD)[:, None] * pilot.cold.PERIOD
    mean = design.mean(axis=1, keepdims=True)
    y_mean = y.mean(axis=1, keepdims=True)
    A = np.concatenate(((design - mean) / (pilot.cold.SHAPE_SD * np.sqrt(samples)),
                        mean / pilot.cold.LEVEL_SD), axis=1)
    b = np.concatenate(((y - y_mean) / (pilot.cold.SHAPE_SD * np.sqrt(samples)),
                        y_mean / pilot.cold.LEVEL_SD), axis=1)
    prior = np.eye(columns)
    prior[0, 0] = prior[1, 1] = pilot.HALF_WIDTH / 1000.
    bounds = np.r_[1., 1., np.full(columns - 2, np.inf)]
    weights = 1. / counts[family]
    for _ in range(pilot.IRLS_STEPS):
        aw = (A * np.sqrt(weights)[:, None, None]).reshape(-1, columns)
        bw = (b * np.sqrt(weights)[:, None]).ravel()
        solution = lsq_linear(np.vstack((aw, prior)), np.r_[bw, np.zeros(columns)],
                              bounds=(-bounds, bounds), method="bvls")
        assert solution.success
        residual = np.linalg.norm(A @ solution.x - b, axis=1)
        weights = np.minimum(1., 2.5 / np.maximum(.01, residual)) / counts[family]
    return solution.x[:n_global]


class ConsensusTests(unittest.TestCase):
    def test_bounded_schur_fit_matches_dense_control(self):
        tracks, bias = fixture()
        stats = pilot.make_stats(tracks, bias, np.zeros(2))
        include = np.ones(len(stats.counts), dtype=bool)
        for fitted in (False, True):
            with self.subTest(fitted=fitted):
                obtained = pilot.fit(stats, include, fitted)
                expected = direct_fit(tracks, bias, fitted)
                np.testing.assert_allclose(obtained[:len(expected)], expected, atol=1.e-9, rtol=0)
                self.assertEqual(obtained[0], 1.)
                if not fitted:
                    self.assertEqual(obtained[10], 0.)

    def test_folds_are_balanced_and_deterministic(self):
        tracks, bias = fixture()
        stats = pilot.make_stats(tracks, bias, np.zeros(2))
        fold = pilot.assign_folds(tracks, stats)
        np.testing.assert_array_equal(fold, pilot.assign_folds(tracks, stats))
        self.assertEqual(len(np.unique(fold)), pilot.FOLDS)
        self.assertLessEqual(np.ptp(np.bincount(fold)), 1)

    def test_duplicates_preserve_both_arms(self):
        tracks, bias = fixture()
        start = np.zeros(2)
        results, cost = pilot.run_consensus(tracks, bias, start)
        self.assertTrue(all(result["status"] == "estimate" for result in results.values()))
        check = pilot.duplicate_check(tracks, bias, start, results)
        self.assertTrue(check["pass_exact"])
        self.assertEqual(cost["unique_tracks"], len(tracks.ids))


if __name__ == "__main__":
    unittest.main()
