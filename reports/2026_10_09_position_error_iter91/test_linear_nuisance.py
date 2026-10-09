"""Independent synthetic bounded-quadratic checks; no recordings or position fits."""

import numpy as np
import pytest
from linear_nuisance import collapse_mixture, receiver_clock_bounds, solve_nuisance_delta
from scipy.optimize import minimize


@pytest.mark.parametrize("seed", [1, 5, 19])
def test_matches_independent_slsqp_quadratic(seed):
    rng = np.random.default_rng(seed)
    design = rng.normal(size=(25, 5))
    residual = rng.normal(size=25) * 4
    weights = rng.uniform(0.1, 2, size=25)
    current = rng.normal(size=5)
    root = rng.normal(size=(5, 5))
    precision = root.T @ root + np.eye(5) * 0.1
    mean = rng.normal(size=5)
    lower, upper = current - 0.3, current + 0.3
    result = solve_nuisance_delta(
        design, residual, weights, current, precision, lower, upper, prior_mean=mean
    )

    def evaluate(coefficients):
        error = design @ (coefficients - current) - residual
        value = 0.5 * np.dot(weights, error**2)
        value += 0.5 * (coefficients - mean) @ precision @ (coefficients - mean)
        gradient = design.T @ (weights * error) + precision @ (coefficients - mean)
        return value, gradient

    reference = minimize(
        evaluate,
        current,
        jac=True,
        method="SLSQP",
        bounds=list(zip(lower, upper, strict=True)),
        options=dict(ftol=1e-12, maxiter=500),
    )
    assert reference.success and result["qualified"]
    np.testing.assert_allclose(result["objective_after"], reference.fun, atol=1e-8)
    np.testing.assert_allclose(result["coefficients"], reference.x, atol=1e-6)


def test_prior_is_on_actual_coefficients_not_zero_centered_delta():
    result = solve_nuisance_delta(
        np.zeros((3, 2)),
        np.zeros(3),
        np.zeros(3),
        np.array([8.0, -4.0]),
        np.eye(2),
        np.full(2, -20.0),
        np.full(2, 20.0),
    )
    assert result["qualified"]
    np.testing.assert_allclose(result["coefficients"], [0, 0], atol=1e-12)
    np.testing.assert_allclose(result["delta"], [-8, 4], atol=1e-12)
    assert result["data_rank"] == 0 and result["regularized_rank"] == 2


def test_rf_and_satellite_locks_are_exact_and_prior_cross_terms_retained():
    current = np.array([1.0, -1.0, 8.0, -3.0, 0.0, 0.0])
    lower, upper = receiver_clock_bounds(current, 2, "zero-c")
    design = np.zeros((3, 6))
    design[:, :2] = [[1, 0], [0, 1], [1, 1]]
    precision = np.eye(6)
    precision[0, 2] = precision[2, 0] = 0.2
    result = solve_nuisance_delta(design, np.ones(3), np.ones(3), current, precision, lower, upper)
    assert result["qualified"] and result["locked_dimensions"] == 4
    np.testing.assert_array_equal(result["coefficients"][2:], current[2:])
    np.testing.assert_allclose(result["gradient"][:2], 0, atol=1e-12)


def test_rank_deficient_unconstrained_case_uses_minimum_change_null_mode():
    design = np.array([[1.0, 1.0, 0.0], [2.0, 2.0, 0.0]])
    current = np.array([2.0, -2.0, 7.0])
    result = solve_nuisance_delta(
        design, [4, 8], [1, 1], current, np.zeros((3, 3)), np.full(3, -100.0), np.full(3, 100.0)
    )
    assert result["qualified"] and result["data_rank"] == 1
    np.testing.assert_allclose(result["delta"], [2, 2, 0], atol=1e-12)


def test_active_box_gradient_has_correct_kkt_sign():
    result = solve_nuisance_delta(
        np.eye(2), [10, -10], [1, 1], np.zeros(2), np.zeros((2, 2)), [-1, -1], [1, 1]
    )
    assert result["qualified"]
    np.testing.assert_allclose(result["coefficients"], [1, -1])
    assert result["gradient"][0] < 0 and result["gradient"][1] > 0
    np.testing.assert_array_equal(result["projected_gradient"], [0, 0])


def test_mixture_collapse_preserves_quadratic_value_and_gradient():
    residual = np.array([[3.0, -2.0], [10.0, 4.0], [99.0, -77.0]])
    probability = np.array([[0.6, 0.2], [0.3, 0.4], [0.0, 0.0]])
    collapsed = collapse_mixture(residual, probability, 125.0)
    update = np.array([1.0, -3.0, 9.0])
    expanded = 0.5 * np.sum(probability * (residual - update[:, None]) ** 2) / 125**2
    compact = 0.5 * np.sum(collapsed["weights"] * (collapsed["residual_hz"] - update) ** 2)
    compact += collapsed["constant"]
    np.testing.assert_allclose(compact, expanded, atol=1e-15)
    np.testing.assert_allclose(
        collapsed["weights"] * (update - collapsed["residual_hz"]),
        np.sum(probability * (update[:, None] - residual), axis=1) / 125**2,
        atol=1e-15,
    )


def test_all_locked_case_and_invalid_precision():
    current = np.array([3.0, 0.0])
    result = solve_nuisance_delta(np.eye(2), [5, 6], [1, 1], current, np.eye(2), current, current)
    assert result["qualified"] and result["locked_dimensions"] == 2
    np.testing.assert_array_equal(result["delta"], [0, 0])
    with pytest.raises(ValueError, match="positive semidefinite"):
        solve_nuisance_delta(
            np.eye(2), [0, 0], [1, 1], np.zeros(2), np.diag([-1.0, 1.0]), [-10, -10], [10, 10]
        )


def test_empty_observation_rows_are_explicitly_rejected():
    with pytest.raises(ValueError, match="invalid bounded quadratic"):
        solve_nuisance_delta(np.zeros((0, 2)), [], [], np.zeros(2), np.eye(2), [-1, -1], [1, 1])


def test_refreshed_wrapped_mixture_objective_acceptance():
    from leo.analysis.hard60_score import likelihood
    from leo.analysis.regional_position_score import ALIAS_HZ, circular
    from leo.contracts.regional_position import POSITION_SCORES

    # Synthetic fixed geometry/visibility, ambiguous candidates plus clutter.
    # Frequencies intentionally straddle the circular observation boundary.
    count = 60
    times = np.linspace(-1, 1, count)
    design = np.column_stack([np.ones(count), times])
    geometry = ALIAS_HZ / 2 - 20 + 800 * np.arange(4)[None, :] + 25 * times[:, None]
    chosen = np.arange(count) % 4
    measurement = circular(geometry[np.arange(count), chosen] + design @ [80.0, -30.0])
    measurement[::11] = circular(measurement[::11] + 5000)  # Synthetic clutter.
    visible = np.ones(geometry.shape, bool)
    score = POSITION_SCORES["V16"]
    current, precision = np.zeros(2), np.eye(2) / 500**2
    before = likelihood(measurement, geometry, visible, score)
    compact = collapse_mixture(before.residual_hz, before.responsibilities, score.sigma_hz)
    step = solve_nuisance_delta(
        design,
        compact["residual_hz"],
        compact["weights"],
        current,
        precision,
        [-1000, -1000],
        [1000, 1000],
        constant=compact["constant"],
    )
    assert step["qualified"]
    candidate = step["coefficients"]
    # Explicitly re-evaluate the actual wrapped mixture: do not accept merely
    # because the quadratic surrogate or its frozen assignments improve.
    refreshed = likelihood(measurement, geometry + (design @ candidate)[:, None], visible, score)
    before_value = before.nll + 0.5 * current @ precision @ current
    candidate_value = refreshed.nll + 0.5 * candidate @ precision @ candidate
    accepted = (
        step["qualified"] and np.isfinite(candidate_value) and candidate_value <= before_value
    )
    assert accepted and candidate_value < before_value - 1
    assert not np.array_equal(refreshed.responsibilities, before.responsibilities)
