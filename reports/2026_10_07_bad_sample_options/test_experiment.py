"""Scientific control checks for selection, timing gauge and convergence audits."""

import unittest

import numpy as np
from leo.analysis.regional_position_score import zero_sum_basis
from experiment import audit, select, timing_trial


class ScientificControls(unittest.TestCase):
    def test_selection_uses_score_even_when_position_truth_disagrees(self):
        rows = [dict(selection_score=10., horizontal_error_m=1., basin="a", origin="saved"),
                dict(selection_score=9., horizontal_error_m=1000., basin="b", origin="fit")]
        self.assertIs(select(rows), rows[1])
        rows[0]["horizontal_error_m"], rows[1]["horizontal_error_m"] = 10000., 0.
        self.assertIs(select(rows), rows[1])

    def test_timing_trial_keeps_all_other_physical_shifts_and_rf_parameters(self):
        basis = zero_sum_basis(4)
        shifts = np.array([1., -2., 4., 5.])
        vector = np.r_[12., -8., 20., .1, 30., -.2, 0., shifts.mean(), basis.T @ shifts]
        original = vector.copy()
        trial = timing_trial(vector, basis, 1)
        wanted = shifts.copy()
        wanted[1] = shifts[[0, 2, 3]].mean()
        np.testing.assert_allclose(trial[7] + basis @ trial[8:], wanted, atol=1e-12)
        np.testing.assert_array_equal(vector, original)
        np.testing.assert_array_equal(trial[:7], original[:7])

    def test_fixed_c_stationarity_is_not_free_c_stationarity(self):
        basis = zero_sum_basis(4)
        vector, gradient = np.zeros(11), np.zeros(11)
        gradient[6] = 2.
        args = (250., np.zeros(2), 12.5, -20., 20.)
        fixed = audit(vector, gradient, basis, "zero-c", *args)
        free = audit(vector, gradient, basis, "fitted-c", *args)
        self.assertTrue(fixed["converged"])
        self.assertFalse(free["converged"])
        self.assertEqual(free["stationarity"], 400.)

    def test_active_spatial_bound_is_included_in_stationarity(self):
        basis = zero_sum_basis(4)
        vector, gradient = np.zeros(11), np.zeros(11)
        vector[0], gradient[0] = 12.5, -3.
        result = audit(vector, gradient, basis, "fitted-c", 250., np.zeros(2), 12.5, -20., 20.)
        self.assertTrue(result["boundary"])
        self.assertTrue(result["converged"])


if __name__ == "__main__":
    unittest.main()
