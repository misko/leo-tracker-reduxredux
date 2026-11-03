"""Prior grid, excluded-measurement isolation, budget and exact freeze tests."""
from dataclasses import replace
from pathlib import Path
import sys
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from test_calibration import toy_context, donor
from portfolio import prior_grid, fit


class PriorPortfolioTests(unittest.TestCase):
    def test_grid_scales_only_with_prior_radius(self):
        context = toy_context()
        grid = prior_grid(context.prior)
        self.assertEqual(grid.shape, (9, 2))
        self.assertTrue(np.all(np.linalg.norm(grid, axis=1) < context.prior.radius_km))
        self.assertEqual(len(np.unique(grid, axis=0)), 9)
        altered = replace(context.prior, radius_km=context.prior.radius_km/2,
            latitude_deg=-20., longitude_deg=80.)
        np.testing.assert_array_equal(prior_grid(altered), grid/2)

    def test_full_held_cfo_invariance_includes_grid_selection_and_fit(self):
        context = toy_context()
        changed = replace(context, observations=replace(context.observations,
            measured_hz=context.observations.measured_hz
            + np.where(context.train_mask, 0., 1234567.)))
        a, da = fit(context, None, max_evaluations=60, max_seconds=15)
        b, db = fit(changed, None, max_evaluations=60, max_seconds=15)
        np.testing.assert_array_equal(a.vector, b.vector)
        np.testing.assert_array_equal(a.nuisance, b.nuisance)
        self.assertEqual(da['seed_objectives'], db['seed_objectives'])
        self.assertEqual(da['ranked_seed_indices'], db['ranked_seed_indices'])
        self.assertEqual(da['selected_seed_index'], db['selected_seed_index'])
        self.assertEqual(da['seed_orbit_projection_calls'], 9)
        self.assertLessEqual(da['evaluations'], 60)
        self.assertEqual(da['evaluations'], da['full_objective_evaluations']
            + da['partial_density_evaluations'])
        self.assertLess(da['correction_transport_max_hz'], 1e-7)
        self.assertLess(da['masked_objective_closure_error'], 1e-7)

    def test_donor_seed_and_c_zero_keep_same_nine_node_policy(self):
        context = toy_context(True)
        trained, diag = fit(context, donor(), use_donor=True,
            max_evaluations=50, max_seconds=15)
        self.assertTrue(diag['donor_used'])
        self.assertEqual(trained.vector[6], 0.)
        self.assertEqual(len(diag['seed_objectives']), 9)
        self.assertLessEqual(len(diag['refinements']), 3)
        self.assertLessEqual(diag['evaluations'], 50)
        self.assertEqual(diag['accepted'], diag['endpoint']['accepted'])


if __name__ == '__main__':
    unittest.main()
