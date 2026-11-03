from __future__ import annotations

import numpy as np
import pytest

from leo.analysis.gaussian_sum_location import Candidate, ObservationFactor, Prediction
from leo.analysis.greedy_joint_location import fit_joint_greedy
from leo.analysis.robust_likelihood import student_t_logpdf


def _factor(identifier, observation, matrix, covariance=0.2):
    matrix = np.asarray(matrix, dtype=float).reshape(1, -1)
    noise = np.array([[covariance]])
    candidate = Candidate(
        identifier, 1.0,
        lambda state: Prediction(matrix @ state, matrix, noise),
    )
    return ObservationFactor((identifier,), np.array([observation]), (candidate,), 0.0, -100.0)


def _score(factor):
    def score(state):
        candidate = factor.candidates[0]
        prediction = candidate.predict(state)
        residual = factor.observation - prediction.mean
        value = -0.5 * (
            np.log(2 * np.pi * prediction.covariance[0, 0])
            + residual[0] ** 2 / prediction.covariance[0, 0]
        )
        return np.array([value, -np.inf])
    return score


def _student_score(factor, nu):
    def score(state):
        candidate = factor.candidates[0]
        prediction = candidate.predict(state)
        return np.array([
            student_t_logpdf(factor.observation - prediction.mean,
                             prediction.covariance, nu),
            -np.inf,
        ])
    return score


def test_affine_joint_state_recovery_and_reorder_invariance() -> None:
    factors = (
        _factor("a", 3.0, [1.0, 1.0]),
        _factor("b", 1.0, [1.0, -1.0]),
    )
    scores = tuple(_score(factor) for factor in factors)
    result = fit_joint_greedy(
        np.array([-4.0, 2.0]), factors, scores, np.array([0.01, 0.01]),
        lambda _state: True,
    )
    reversed_result = fit_joint_greedy(
        np.array([-4.0, 2.0]), tuple(reversed(factors)), tuple(reversed(scores)),
        np.array([0.01, 0.01]), lambda _state: True,
    )
    np.testing.assert_allclose(result.mean, [1.995, 0.9975], atol=0.01)
    np.testing.assert_allclose(reversed_result.mean, result.mean, atol=1e-12)
    assert result.converged


def test_starting_proposal_is_not_used_as_gaussian_prior_mean() -> None:
    factor = _factor("a", 0.0, [1.0])
    result = fit_joint_greedy(
        np.array([8.0]), (factor,), (_score(factor),), np.array([1.0]),
        lambda _state: True,
    )
    assert abs(result.mean[0]) < 1e-8
    shifted = fit_joint_greedy(
        np.array([8.0]), (factor,), (_score(factor),), np.array([1.0]),
        lambda _state: True, prior_mean=np.array([2.0]),
    )
    assert shifted.mean[0] > 0.0


def test_duplicate_physical_observations_are_rejected() -> None:
    first = _factor("same", 0.0, [1.0])
    second = _factor("other", 1.0, [1.0])
    second = ObservationFactor(first.observation_ids, second.observation,
                               second.candidates, second.background_prior,
                               second.background_log_likelihood)
    with pytest.raises(ValueError, match="must not be reused"):
        fit_joint_greedy(np.zeros(1), (first, second), (_score(first), _score(second)),
                         np.ones(1), lambda _state: True)


def test_all_background_and_stalled_search_do_not_claim_convergence() -> None:
    original = _factor("a", 0.0, [1.0])
    candidate = Candidate("a", 0.0, original.candidates[0].predict)
    factor = ObservationFactor(("a",), original.observation, (candidate,), 1.0, -100.0)
    def background(_state):
        return np.array([-np.inf, -100.0])

    result = fit_joint_greedy(np.zeros(1), (factor,), (background,), np.ones(1),
                              lambda _state: True)
    assert not result.converged and result.reason == "all_background"
    assert result.associations == (1,)

    stalled_factor = _factor("b", 2.0, [1.0])
    stalled = fit_joint_greedy(
        np.zeros(1), (stalled_factor,), (_score(stalled_factor),), np.zeros(1),
        lambda state: state[0] == 0.0,
    )
    assert not stalled.converged and stalled.reason == "line_search_stalled"


def test_fast_source_score_must_match_selected_physical_branch() -> None:
    factor = _factor("a", 0.0, [1.0])
    def wrong(_state):
        return np.array([123.0, -np.inf])

    with pytest.raises(ValueError, match="selected physical score"):
        fit_joint_greedy(np.zeros(1), (factor,), (wrong,), np.ones(1), lambda _state: True)


def test_tiny_objective_change_with_large_step_does_not_claim_stable_convergence() -> None:
    noise = np.array([[1e6]])

    def flat_nonlinear(state):
        mean = np.array([1e-3 * np.exp(state[0] / 100.0)])
        jacobian = np.array([[mean[0] / 100.0]])
        return Prediction(mean, jacobian, noise)

    candidate = Candidate(
        "flat", 1.0, flat_nonlinear,
    )
    factor = ObservationFactor(("flat",), np.array([1.0]), (candidate,), 0.0, -100.0)
    scorer = _score(factor)
    result = fit_joint_greedy(
        np.zeros(1), (factor,), (scorer,), np.zeros(1), lambda _state: True,
        max_iterations=2, max_spatial_step=1.0,
    )
    assert result.accepted_step_norms == pytest.approx((1.0, 1.0))
    assert not result.converged
    assert result.reason == "iteration_limit"


def test_student_t_reduces_outlier_bias_and_decreases_its_objective() -> None:
    factors = tuple(_factor(str(index), value, [1.0], covariance=1.0)
                    for index, value in enumerate((0.0, 0.0, 100.0)))
    gaussian = fit_joint_greedy(
        np.zeros(1), factors, tuple(_score(factor) for factor in factors),
        np.zeros(1), lambda _state: True,
    )
    robust = fit_joint_greedy(
        np.zeros(1), factors, tuple(_student_score(factor, 4.0) for factor in factors),
        np.zeros(1), lambda _state: True, degrees_of_freedom=4.0,
    )
    assert abs(robust.mean[0]) < 1.0
    assert abs(robust.mean[0]) < abs(gaussian.mean[0]) / 10
    assert all(right < left for left, right in zip(
        robust.objectives, robust.objectives[1:], strict=False
    ))
