import sys
from collections import Counter
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase

import numpy as np


sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
from grid_predictive_precision import guarded_predictor, predictive_precision
from grid_predictive_reduction import reduced_predictive


class PredictivePrecisionTest(TestCase):
    def test_same_objective_and_residual_with_permuted_latent_scales(self):
        rng = np.random.default_rng(19)
        width = 11
        lower = 4 * np.eye(width) + np.tril(rng.normal(size=(width, width)), -1)
        capture = SimpleNamespace(width=width, lower=lower, order=rng.permutation(width))
        groups = np.repeat(np.array([2, 8, 10]), [12, 1, 8])
        sigma = np.geomspace(0.8, 100., len(groups))
        raw = rng.normal(size=len(groups))
        design = rng.normal(size=(len(groups), width))
        original, _ = reduced_predictive(raw, design, sigma, groups, capture, 3, include_residual=True)
        candidate = predictive_precision(raw, design, sigma, groups, capture, 3, check_condition=True)
        self.assertEqual(candidate["normalization_constant"], original["normalization_constant"])
        self.assertAlmostEqual(candidate["objective"], original["objective"], places=10)
        np.testing.assert_allclose(candidate["residual"], original["residual"], atol=1e-11, rtol=1e-10)

    def test_refuses_unsorted_group_labels(self):
        with self.assertRaises(ValueError):
            predictive_precision(np.ones(2), np.ones((2, 1)), np.ones(2), np.array([2, 1]),
                                 SimpleNamespace(width=1), 1)

    def test_condition_and_compact_residual_fall_back_to_incumbent(self):
        counts = Counter()
        incumbent = object()
        evaluate = guarded_predictor(lambda *args, **kw: incumbent, counts)
        capture = SimpleNamespace(width=2, lower=np.diag([1e8, 1.]),
                                  order=np.arange(2), valid=lambda: True)
        measurements = np.ones(3)
        keys = np.zeros(3, dtype=np.int64)
        design = np.ones((3, 2))
        self.assertIs(evaluate(measurements, design, measurements, keys, capture, 1,
                               include_residual=True), incumbent)
        design[:, 0] = 0
        self.assertIs(evaluate(measurements, design, measurements, keys, capture, 1,
                               include_residual=True), incumbent)
        self.assertEqual(counts, {"rejected_or_unsupported": 1, "original_compact_layout": 1, "incumbent": 2})
