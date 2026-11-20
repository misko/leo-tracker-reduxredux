"""Verify the bounded least-squares model and its physical stopping diagnostic."""

import numpy as np
import pytest

from leo.analysis.research.continuous_curve_fit import bounded_gauss_newton
from tools.pipeline_eval.variants.v5_secant_fit import STOP_KM, _slope_receipt, bounded_secant


def _measure(solver, objective, initial, lower, upper):
    evaluated = []

    def residual(position):
        assert np.all((lower <= position) & (position <= upper))
        evaluated.append(position.copy())
        return objective(position)

    fit = solver(residual, initial, lower, upper, iterations=48)
    assert fit["evaluations"] == len(evaluated)
    assert fit["score"] == pytest.approx(np.sum(objective(fit["parameters"]) ** 2))
    history = fit["history"]
    assert all(b["score"] < a["score"] for a, b in zip(history, history[1:], strict=False))
    np.testing.assert_array_equal(history[-1]["parameters"], fit["parameters"])
    return fit


def test_weighted_quadratic_reaches_analytic_solution_with_fewer_evaluations():
    matrix = np.array([[4.0, 2.0], [0.0, 3.0], [1.0, 1.0]])
    target = np.array([7.1, -1.2])

    def residual(position):
        return matrix @ (position - target)

    lower, upper, center = np.full(2, -12.5), np.full(2, 12.5), np.zeros(2)
    new = _measure(bounded_secant, residual, center, lower, upper)
    control = _measure(bounded_gauss_newton, residual, center, lower, upper)
    np.testing.assert_allclose(new["parameters"], target, atol=STOP_KM)
    assert new["secant_updates"] >= 1
    assert new["stopped"] == "small_bounded_step"
    assert new["evaluations"] < control["evaluations"]


def test_active_boundary_reoptimizes_tangential_coordinate():
    matrix = np.array([[2.0, 1.0], [0.0, 2.0], [1.0, 2.0]])
    target = np.array([4.0, 0.3])
    normal = matrix.T @ matrix
    optimum = [2.0, target[1] + normal[1, 0] * (target[0] - 2.0) / normal[1, 1]]

    fit = _measure(
        bounded_secant,
        lambda position: matrix @ (position - target),
        np.array([5.0, -4.0]),
        np.full(2, -2.0),
        np.full(2, 2.0),
    )

    np.testing.assert_allclose(fit["parameters"], optimum, atol=STOP_KM)
    assert fit["parameters"][0] == 2


def test_rank_deficient_geometry_limits_steps_to_identifiable_direction():
    fit = _measure(
        bounded_secant,
        lambda position: np.array([position[0] - 2.0, 2.0 * position[0] - 4.0]),
        np.array([-3.0, 1.7]),
        np.full(2, -5.0),
        np.full(2, 5.0),
    )
    np.testing.assert_allclose(fit["parameters"], [2.0, 1.7], atol=STOP_KM)
    flat = _measure(
        bounded_secant, lambda _: np.array([17.0]), np.ones(2), np.zeros(2), np.full(2, 2.0)
    )
    np.testing.assert_array_equal(flat["parameters"], np.ones(2))
    assert flat["evaluations"] == 3
    assert flat["stopped"] == "small_bounded_step"


def test_conditional_doppler_slope_respects_the_fit_mask_and_tile():
    class Problem:
        keep = np.array([True, False, True])
        point_noise = np.array([40.0, 300.0, 60.0])
        lower = np.full(2, -12.5)
        upper = np.full(2, 12.5)

        def calculate(self, position):
            assert np.all((self.lower <= position) & (position <= self.upper))
            rates = np.array([[3.0, 4.0], [100.0, 200.0], [5.0, 12.0]])
            return dict(conditional_residual_hz=rates @ position)

    result = _slope_receipt(Problem(), np.array([12.5, 0.0]))
    assert result["points"] == 2
    assert result["median_hz_per_km"] == pytest.approx(9)
    assert result["p95_20m_hz"] == pytest.approx(0.252)
    assert result["median_nominal_point_noise_hz"] == 50
