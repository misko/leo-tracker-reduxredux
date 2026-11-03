"""Synthetic constrained quadratic audits of the report-only slope prototype."""

from dataclasses import fields
from types import SimpleNamespace
import unittest

import numpy as np

from bounded_fit import fit_position
from leo.analysis.regional_position_fit import fit_position as production_fit


class QuadraticObjective:
    size = 9

    def __init__(self, target=None):
        self.target = np.zeros(self.size) if target is None else np.asarray(target, float)
        self.prior = SimpleNamespace(radius_km=100.0)
        self.bank = SimpleNamespace(numbers=(1, 2), nodes_s=np.array([-100.0, 100.0]))
        self.observations = SimpleNamespace(times_s=np.array([-1.0, 1.0]))
        self.basis = np.array([[1.0], [-1.0]]) / np.sqrt(2.0)
        # Equal curvature in the deployed optimizer's scaled coordinates.
        self.scales = np.array([1.0, 1.0, 200.0, 2.0, 200.0, 2.0, 200.0, 1.0, 1.0])
        self.history = []

    def evaluate(self, vector):
        self.history.append(vector.copy())
        residual = vector - self.target
        gradient = residual / self.scales**2
        value = 0.5 * float(residual @ gradient)
        terms = SimpleNamespace(
            responsibilities=np.ones((2, 2)), residual_hz=np.zeros((2, 2))
        )
        return value, gradient, terms


class SlopeBoundsTest(unittest.TestCase):
    def test_each_receiver_upper_and_lower_bound_has_correct_kkt(self):
        for index in (3, 5):
            for sign in (-1.0, 1.0):
                for width in (10.0, 30.0, 60.0):
                    with self.subTest(index=index, sign=sign, width=width):
                        target = np.zeros(9)
                        target[index] = sign * (width + 20.0)
                        objective = QuadraticObjective(target)
                        result = fit_position(objective, np.zeros(9), slope_half_width_hz_s=width)
                        expected = np.zeros(9)
                        expected[index] = sign * width
                        np.testing.assert_allclose(result.vector, expected, atol=1e-6)
                        self.assertAlmostEqual(result.objective, 50.0, places=5)
                        self.assertLess(result.stationarity, 1e-6)
                        self.assertTrue(result.converged)
                        # The outward optimum leaves a nonzero raw gradient;
                        # convergence therefore requires the correct bound normal.
                        self.assertGreater(abs(objective.evaluate(result.vector)[1][index]), 1)

    def test_none_preserves_production_fit_and_objective_history(self):
        target = np.array([2, -3, 150, 80, -120, -100, 700, 2, 1], float)
        start = np.array([1, -1, 0, -70, 0, 90, 200, -1, -2], float)
        prototype_objective, deployed_objective = QuadraticObjective(target), QuadraticObjective(target)
        prototype = fit_position(prototype_objective, start)
        deployed = production_fit(deployed_objective, start)
        np.testing.assert_array_equal(prototype.vector, deployed.vector)
        np.testing.assert_array_equal(prototype_objective.history, deployed_objective.history)
        for field in fields(prototype):
            if field.name not in ("vector", "elapsed_s"):
                self.assertEqual(getattr(prototype, field.name), getattr(deployed, field.name))
        self.assertGreater(abs(prototype.vector[3]), 60)
        self.assertGreater(abs(prototype.vector[5]), 60)

    def test_zero_c_is_fixed_at_every_evaluation(self):
        target = np.array([0, 0, 100, 120, -100, -140, 2500, 0, 0], float)
        start = np.array([0, 0, 200, -200, -300, 200, 4300, 0, 0], float)
        objective = QuadraticObjective(target)
        result = fit_position(objective, start, rf_arm="zero-c", slope_half_width_hz_s=60)
        self.assertEqual(result.vector[6], 0)
        self.assertTrue(all(vector[6] == 0 for vector in objective.history))
        np.testing.assert_allclose(result.vector[[3, 5]], [60, -60], atol=1e-6)
        self.assertLess(result.stationarity, 1e-6)

    def test_invalid_width_is_rejected_before_evaluation(self):
        for width in (0, -1, np.nan, np.inf, -np.inf, True, np.bool_(True), "10", [10], 1j):
            with self.subTest(width=width):
                objective = QuadraticObjective()
                with self.assertRaisesRegex(ValueError, "slope half width"):
                    fit_position(objective, np.zeros(9), slope_half_width_hz_s=width)
                self.assertEqual(objective.history, [])

    def test_start_clips_only_new_slope_coordinates_and_preserves_input(self):
        start = np.array([2, -3, 120, -200, -140, 300, 700, 2, 1], float)
        original = start.copy()
        objective = QuadraticObjective()
        fit_position(objective, start, maximum_iterations=1, slope_half_width_hz_s=30)
        expected = original.copy()
        expected[[3, 5]] = [-30, 30]
        np.testing.assert_array_equal(objective.history[0], expected)
        np.testing.assert_array_equal(start, original)

    def test_existing_local_disk_timing_and_c_bounds_remain_active(self):
        target = np.array([20, 0, 0, 200, 0, -200, 8000, 40, 0], float)
        objective = QuadraticObjective(target)
        result = fit_position(
            objective, np.zeros(9), local_center=np.zeros(2), local_radius_km=5,
            slope_half_width_hz_s=30,
        )
        np.testing.assert_allclose(result.vector[[0, 3, 5, 6, 7]], [5, 30, -30, 5000, 10], atol=1e-4)
        self.assertTrue(result.boundary)
        self.assertLess(result.stationarity, 1e-4)
        # Exercise orbit-shift inequalities independently of the common-tau box.
        target[7], target[8], target[6], target[0] = 0, 40, 0, 0
        result = fit_position(QuadraticObjective(target), np.zeros(9), slope_half_width_hz_s=30)
        np.testing.assert_allclose(result.vector[8], 20 * np.sqrt(2), atol=1e-4)
        self.assertLess(result.stationarity, 1e-4)

    def test_fixed_position_is_preserved(self):
        start = np.array([2, -3, 0, 100, 0, -100, 0, 0, 0], float)
        result = fit_position(QuadraticObjective(), start, fixed_position=True, slope_half_width_hz_s=10)
        np.testing.assert_array_equal(result.vector[:2], start[:2])
        self.assertLess(result.stationarity, 1e-6)


if __name__ == "__main__":
    unittest.main(verbosity=2)
