"""Unit checks for the private exact fixed-scaffolding components."""

from hashlib import sha256
from inspect import getsource
from types import SimpleNamespace
import unittest

import numpy as np
from scipy.linalg import solve_triangular

from leo.analysis.localization_v3 import history_position, predictive_linear

from grid_fixed_context import PredictiveByView, curved_factory


def whiten(design, lower, order, scales):
    return solve_triangular(lower, (design[:, order] * scales[order]).T,
                            lower=True, check_finite=False).T


def ordinary(raw, design, sigma, groups, capture, member_count):
    scale = np.ones(capture.width)
    scale[-member_count:] = .3
    uncertainty = whiten(design, capture.lower, capture.order, scale)
    biases = np.zeros((len(raw), int(groups.max()) + 1))
    biases[np.arange(len(raw)), groups] = 300.
    features = np.column_stack((uncertainty, biases))
    return predictive_linear.conditional_gaussian(
        raw, features, sigma, np.ones(len(raw)), np.ones(len(raw)), np.ones(features.shape[1]), 1.)


class FixedGridContextTest(unittest.TestCase):
    def setUp(self):
        rng = np.random.default_rng(25)
        self.design = rng.normal(size=(31, 9))
        self.raw = rng.normal(size=31) * 350.
        self.sigma = rng.uniform(40., 300., size=31)
        self.groups = np.arange(31) % 5
        self.capture = SimpleNamespace(width=9, lower=np.linalg.cholesky(
            self.design.T @ self.design + np.eye(9)), order=rng.permutation(9))
        self.candidate = PredictiveByView(ordinary, whiten)

    def compare(self, raw, design, sigma, groups, member_count):
        args = raw, design, sigma, groups, self.capture, member_count
        expected, got = ordinary(*args), self.candidate(*args)
        self.assertEqual(expected.keys(), got.keys())
        for key in expected:
            a, b = expected[key], got[key]
            if isinstance(a, np.ndarray):
                self.assertEqual((a.shape, a.dtype, a.tobytes()), (b.shape, b.dtype, b.tobytes()), key)
            else:
                self.assertEqual(a, b, key)

    def test_fixed_rows_and_current_posterior_keep_every_output_exact(self):
        self.compare(self.raw, self.design, self.sigma, self.groups, 3)
        self.capture.order[:] = self.capture.order[::-1]
        self.capture.lower += np.eye(9)
        self.compare(-self.raw, self.design + 0.07, self.sigma.copy(), self.groups, 3)
        self.compare(-self.raw, self.design + 0.07, self.sigma.copy(), self.groups.copy(), 3)
        self.assertEqual(self.candidate.counts["prepared_calls"], 3)
        self.assertEqual(self.candidate.counts["prepared_views"], 2)

    def test_changed_noise_uses_ordinary_fallback(self):
        self.compare(self.raw, self.design, self.sigma, self.groups, 2)
        self.compare(self.raw, self.design, self.sigma + 1., self.groups, 2)
        self.assertEqual(self.candidate.counts["original_calls"], 1)

    def test_nonfinite_operands_preserve_ordinary_error(self):
        raw = self.raw.copy()
        raw[0] = np.inf
        with self.assertRaisesRegex(ValueError, "finite values"):
            self.candidate(raw, self.design, self.sigma, self.groups, self.capture, 2)
        self.assertEqual(self.candidate.counts["original_calls"], 1)

    def test_curved_factory_checks_original_source_and_boundary(self):
        function = history_position.make_problem
        with self.assertRaisesRegex(ValueError, "Unreviewed"):
            curved_factory(function, "wrong")
        candidate = curved_factory(function, sha256(getsource(function).encode()).hexdigest())
        self.assertIsNot(candidate, function)
        self.assertEqual(candidate.__name__, function.__name__)


if __name__ == "__main__":
    unittest.main()
