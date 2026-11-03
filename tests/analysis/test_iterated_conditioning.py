from __future__ import annotations

import numpy as np
import pytest

from leo.analysis.gaussian_sum_location import GaussianComponent, Prediction
from leo.analysis.iterated_conditioning import (
    IteratedConditioningConfig,
    condition_iterated,
    condition_joint_iterated,
)


def test_affine_model_matches_one_exact_gaussian_conditioning() -> None:
    parent = GaussianComponent(1.0, np.array([0.0]), np.array([[4.0]]))

    def predictor(state):
        return Prediction(state.copy(), np.ones((1, 1)), np.array([[1.0]]))

    result = condition_iterated(parent, np.array([2.0]), predictor)
    np.testing.assert_allclose(result.component.mean, [1.6], atol=1e-12)
    np.testing.assert_allclose(result.component.covariance, [[0.8]], atol=1e-12)


def test_nonlinear_damping_decreases_objective_without_overshoot() -> None:
    parent = GaussianComponent(1.0, np.array([0.0]), np.array([[9.0]]))

    def predictor(state):
        value = np.exp(state[0])
        return Prediction(np.array([value]), np.array([[value]]), np.array([[0.04]]))

    result = condition_iterated(
        parent, np.array([np.exp(2.0)]), predictor,
        IteratedConditioningConfig(geographic_indices=(0,), maximum_geographic_step=0.5),
    )
    assert all(a > b for a, b in zip(result.objectives, result.objectives[1:], strict=False))
    assert 1.8 < result.mode[0] < 2.0
    assert result.converged


def test_more_iterations_do_not_reconsume_the_same_affine_factor() -> None:
    parent = GaussianComponent(1.0, np.array([0.0]), np.array([[2.0]]))

    def predictor(state):
        return Prediction(2.0 * state, np.array([[2.0]]), np.array([[3.0]]))

    one = condition_iterated(parent, np.array([1.0]), predictor,
                             IteratedConditioningConfig(max_iterations=1))
    many = condition_iterated(parent, np.array([1.0]), predictor,
                              IteratedConditioningConfig(max_iterations=12))
    np.testing.assert_allclose(one.component.covariance, many.component.covariance, atol=1e-14)


def test_inactive_mean_and_full_covariance_preserve_prior_cross_correlation() -> None:
    covariance = np.array([[2.0, 0.8], [0.8, 3.0]])
    parent = GaussianComponent(1.0, np.zeros(2), covariance)

    def predictor(state):
        return Prediction(np.array([state[0]]), np.array([[1.0, 0.0]]), np.array([[1.0]]))

    result = condition_iterated(parent, np.array([3.0]), predictor)
    assert result.active_indices == (0,)
    assert result.component.mean[1] != 0.0
    assert result.component.covariance[0, 1] != 0.0
    np.linalg.cholesky(result.component.covariance)


def test_infeasible_trial_is_rejected_without_clipping() -> None:
    parent = GaussianComponent(1.0, np.array([0.0]), np.array([[4.0]]))

    def predictor(state):
        return Prediction(np.array([state[0]]), np.ones((1, 1)), np.array([[0.01]]))

    result = condition_iterated(
        parent, np.array([2.0]), predictor,
        IteratedConditioningConfig(max_iterations=3), support=lambda state: state[0] < 1.5,
    )
    assert result.mode[0] < 1.5
    assert result.rejected_steps > 0


def test_initial_mode_selects_nonlinear_basin_without_shifting_original_prior() -> None:
    parent = GaussianComponent(1.0, np.array([0.0]), np.array([[4.0]]))

    def predictor(state):
        return Prediction(np.array([state[0] ** 2]), np.array([[2.0 * state[0]]]),
                          np.array([[0.05]]))

    positive = condition_iterated(parent, np.array([4.0]), predictor, initial_mode=np.array([1.0]))
    negative = condition_iterated(parent, np.array([4.0]), predictor, initial_mode=np.array([-1.0]))
    assert positive.mode[0] > 0.0 and negative.mode[0] < 0.0
    assert abs(positive.mode[0]) == pytest.approx(abs(negative.mode[0]), rel=1e-10)
    np.testing.assert_array_equal(parent.mean, [0.0])
    assert positive.objectives[-1] == pytest.approx(negative.objectives[-1], abs=1e-12)


def test_joint_affine_condition_matches_stacked_analytic_and_is_reorder_invariant() -> None:
    covariance = np.array([[2.0, 0.6], [0.6, 3.0]])
    parent = GaussianComponent(1.0, np.array([0.2, -0.3]), covariance)
    matrices = (np.array([[1.0, 0.5]]), np.array([[-0.2, 1.0]]))
    noises = (np.array([[0.7]]), np.array([[1.3]]))
    observations = (np.array([1.2]), np.array([-0.8]))

    def make_predictor(matrix, noise):
        return lambda state: Prediction(matrix @ state, matrix, noise)

    predictors = tuple(make_predictor(matrix, noise)
                       for matrix, noise in zip(matrices, noises, strict=True))
    result = condition_joint_iterated(parent, observations, predictors)
    h = np.concatenate(matrices, axis=0)
    r = np.diag([0.7, 1.3])
    gain = covariance @ h.T @ np.linalg.inv(h @ covariance @ h.T + r)
    expected_mean = parent.mean + gain @ (np.concatenate(observations) - h @ parent.mean)
    expected_covariance = covariance - gain @ h @ covariance
    np.testing.assert_allclose(result.component.mean, expected_mean, atol=1e-12)
    np.testing.assert_allclose(result.component.covariance, expected_covariance, atol=1e-12)
    reversed_result = condition_joint_iterated(
        parent, tuple(reversed(observations)), tuple(reversed(predictors))
    )
    np.testing.assert_allclose(reversed_result.component.mean, result.component.mean, atol=1e-12)
    np.testing.assert_allclose(
        reversed_result.component.covariance, result.component.covariance, atol=1e-12
    )
