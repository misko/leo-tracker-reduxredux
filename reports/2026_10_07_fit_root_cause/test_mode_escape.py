"""Physical-coordinate integrity of the timing intervention."""

import unittest

import numpy as np
from leo.analysis.regional_position_score import zero_sum_basis
from mode_escape import common_mode_trial


class TimingModeTests(unittest.TestCase):
    def test_changes_only_one_physical_satellite_shift(self):
        basis = zero_sum_basis(4)
        shifts = np.array([2.0, -3.0, 4.0, 5.0])
        vector = np.r_[12.0, -8.0, 20.0, .1, 30.0, -.2, 15.0,
                       shifts.mean(), basis.T @ shifts]
        original = vector.copy()
        trial = common_mode_trial(vector, basis, 1)
        expected = shifts.copy()
        expected[1] = shifts[[0, 2, 3]].mean()
        np.testing.assert_allclose(trial[7] + basis @ trial[8:], expected, atol=1e-12)
        np.testing.assert_array_equal(vector, original)
        np.testing.assert_array_equal(trial[:7], original[:7])

    def test_preserves_zero_c_and_zero_sum_gauge(self):
        basis = zero_sum_basis(5)
        shifts = np.array([-12.0, 1.0, 3.0, 4.0, 5.0])
        vector = np.r_[np.zeros(7), shifts.mean(), basis.T @ shifts]
        for index in range(5):
            trial = common_mode_trial(vector, basis, index)
            self.assertEqual(trial[6], 0.0)
            self.assertAlmostEqual(float((basis @ trial[8:]).sum()), 0.0)


if __name__ == "__main__":
    unittest.main()
