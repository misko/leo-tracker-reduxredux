"""Cached conditional likelihood physics and excluded-value invariance."""
from dataclasses import replace
import unittest
import numpy as np
from conditional import FixedResidualLikelihood, fit_bias_only, masked_baseline
from model import ConstantBiasObjective
from test_model import toy


class ConditionalTests(unittest.TestCase):
    def test_cached_value_gradient_and_profile_match_full_bias_model(self):
        ctx = toy(masked=True)
        base = masked_baseline(ctx.full_model, ctx.observations, ctx.train_mask)
        cached = FixedResidualLikelihood(base, ctx.vector, ctx.nuisance, 300.)
        full = ConstantBiasObjective(base, 300.)
        b = np.array([100., -50., 20.])
        value, gradient = cached.evaluate(b)
        expected = full.evaluate_joint(ctx.vector, np.r_[ctx.nuisance, b])
        self.assertAlmostEqual(value, expected[0], places=9)
        np.testing.assert_allclose(gradient, expected[2][-3:], atol=1e-12)
        proposed = np.array([-1000., 500., 4000.])
        scores = cached.profile(b, proposed)
        for k in range(3):
            trial = b.copy()
            trial[k] = proposed[k]
            self.assertAlmostEqual(scores[k], cached.evaluate(trial)[0], places=9)

    def test_held_measured_cfo_full_fit_invariance_and_budget(self):
        ctx = toy(masked=True)
        changed = replace(ctx.observations, measured_hz=ctx.observations.measured_hz
            +np.where(ctx.train_mask, 0., 1234567.))
        first = masked_baseline(ctx.full_model, ctx.observations, ctx.train_mask)
        second = masked_baseline(ctx.full_model, changed, ctx.train_mask)
        a = FixedResidualLikelihood(first, ctx.vector, ctx.nuisance, 1000.)
        b = FixedResidualLikelihood(second, ctx.vector, ctx.nuisance, 1000.)
        aa, ad = fit_bias_only(a, max_evaluations=40, max_seconds=10)
        bb, bd = fit_bias_only(b, max_evaluations=40, max_seconds=10)
        np.testing.assert_array_equal(aa, bb)
        self.assertEqual(ad['final_train_objective'], bd['final_train_objective'])
        self.assertLessEqual(ad['density_evaluations'], 40)
        self.assertEqual(ad['density_evaluations'], bd['density_evaluations'])
        self.assertTrue(ad['final_positions_unchanged'])

    def test_signed_residual_prediction_and_bounded_prior(self):
        ctx = toy(masked=True)
        likelihood = FixedResidualLikelihood(ctx.model, ctx.vector, ctx.nuisance, 1000.)
        b, diagnostics = fit_bias_only(likelihood, max_evaluations=100, max_seconds=10)
        self.assertLess(diagnostics['final_train_objective'], diagnostics['initial_train_objective'])
        np.testing.assert_allclose(b, [180., -140., 90.], atol=15.)
        with self.assertRaises(ValueError):
            likelihood.evaluate(np.array([np.nan, 0., 0.]))


if __name__ == '__main__':
    unittest.main()
