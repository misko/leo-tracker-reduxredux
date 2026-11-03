from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pytest

from leo.analysis.gaussian_sum_location import Prediction
from leo.analysis.localization_fast import fit_localization_fast
from leo.analysis.localization_profiled import (
    effective_shift_precision,
    effective_shifts,
    fit_localization_profiled,
    reconstruct_profiled_state,
    solve_shared_drift,
)
from leo.analysis.robust_likelihood import student_t_logpdf


def _prior(state, precision, center):
    delta = state - center
    return 0.5 * np.dot(precision * delta, delta)


def test_effective_shift_is_gauge_invariant() -> None:
    state = np.array([2., -3., .4, .1, -.2, -.7, 1.2, .3])
    shifted = state.copy()
    shifted[2] += .375
    shifted[5:] -= .375
    np.testing.assert_array_equal(effective_shifts(shifted), effective_shifts(state))


def test_rank_one_precision_matches_dense_inverse() -> None:
    clock_variance = 1.7
    epoch_variances = np.array([.2, .8, 2.3, .4])
    actual = effective_shift_precision(
        1 / clock_variance, 1 / epoch_variances
    )
    covariance = np.diag(epoch_variances) + clock_variance
    np.testing.assert_allclose(actual, np.linalg.inv(covariance), rtol=2e-14, atol=2e-14)


def test_reconstruction_is_original_prior_minimum_and_preserves_constant() -> None:
    precision = np.array([.2, .3, 1 / 1.7, .5, .7, 1 / .2, 1 / .8, 1 / 2.3])
    center = np.array([1., -2., .15, -.1, .3, .2, -.4, .7])
    shifts = np.array([-.3, .8, 1.4])
    state = reconstruct_profiled_state(
        np.array([8., 9.]), np.array([.6, -.2]), shifts, precision, center
    )
    np.testing.assert_allclose(effective_shifts(state), shifts)
    grid = state[2] + np.linspace(-2., 2., 1001)
    alternatives = np.array([
        np.r_[state[:2], clock, state[3:5], shifts - clock] for clock in grid
    ])
    values = np.array([_prior(item, precision, center) for item in alternatives])
    assert _prior(state, precision, center) == pytest.approx(values.min(), abs=2e-6)

    effective_center = center[2] + center[5:]
    rank_one = effective_shift_precision(precision[2], precision[5:])
    profiled_part = .5 * (shifts - effective_center) @ rank_one @ (shifts - effective_center)
    untouched = .5 * np.dot(
        precision[[0, 1, 3, 4]] * (state[[0, 1, 3, 4]] - center[[0, 1, 3, 4]]),
        state[[0, 1, 3, 4]] - center[[0, 1, 3, 4]],
    )
    assert _prior(state, precision, center) == pytest.approx(profiled_part + untouched)


def test_shared_drift_normal_equations_match_dense_stack() -> None:
    observations = (np.array([4., -1.]), np.array([1.5]))
    means = (np.array([1., 2.]), np.array([-.5]))
    designs = (np.array([[1., 2.], [3., -1.]]), np.array([[2., .5]]))
    covariances = (np.array([[2., .3], [.3, 1.]]), np.array([[.7]]))
    weights = (0.4, 1.7)
    precision = np.array([.8, 1.2])
    center = np.array([.2, -.3])
    actual = solve_shared_drift(
        observations, means, designs, covariances, weights, precision, center
    )
    system = np.diag(precision)
    rhs = precision * center
    for y, mean, design, covariance, weight in zip(
        observations, means, designs, covariances, weights, strict=True
    ):
        system += weight * design.T @ np.linalg.solve(covariance, design)
        rhs += weight * design.T @ np.linalg.solve(covariance, y - mean)
    np.testing.assert_allclose(actual, np.linalg.solve(system, rhs), atol=1e-13)


def test_shared_drift_does_not_give_each_track_an_independent_error() -> None:
    shared = solve_shared_drift(
        (np.array([3.]), np.array([-3.])),
        (np.zeros(1), np.zeros(1)),
        (np.ones((1, 2)), np.ones((1, 2))),
        (np.eye(1), np.eye(1)), (1., 1.), np.ones(2),
    )
    independent = [solve_shared_drift(
        (np.array([value]),), (np.zeros(1),), (np.ones((1, 2)),),
        (np.eye(1),), (1.,), np.ones(2),
    ) for value in (3., -3.)]
    np.testing.assert_allclose(shared, 0., atol=1e-14)
    assert np.linalg.norm(independent[0] - independent[1]) > 1.


@dataclass
class _LinearPort:
    observation_ids: tuple[str, ...]
    observation: np.ndarray
    candidate_count: int
    candidate: int
    noise: float = .2
    background: float = -100.
    nu: float | None = None
    priors_piecewise_constant: bool = True

    def predict_selected(self, state, index):
        assert 0 <= index < self.candidate_count
        row = np.zeros(state.size)
        row[0] = 1.
        row[3] = 1.
        row[4] = 2.
        row[2] = 1.
        row[5 + index] = 1.
        return Prediction(
            np.array([row @ state]), row[None, :], np.array([[self.noise]])
        )

    def score_all(self, state):
        result = np.full(self.candidate_count + 1, -np.inf)
        result[self.candidate] = self.score_selected(state, self.candidate)
        result[-1] = self.background
        return result

    def score_selected(self, state, index):
        if index == self.candidate_count:
            return float(self.background)
        if index != self.candidate:
            return -np.inf
        prediction = self.predict_selected(state, self.candidate)
        residual = self.observation - prediction.mean
        if self.nu is None:
            return float(-.5 * (
                np.log(2 * np.pi * self.noise) + residual[0] ** 2 / self.noise
            ))
        return student_t_logpdf(residual, prediction.covariance, self.nu)


def test_profiled_optimizer_decreases_original_objective_and_keeps_inactive_epoch() -> None:
    ports = (
        _LinearPort(("a",), np.array([4.]), 3, 0),
        _LinearPort(("b",), np.array([-1.]), 3, 1),
    )
    initial = np.array([-3., 2., .6, 0., 0., -.4, .2, 5.])
    precision = np.array([.1, .1, 1., .5, .5, 4., 4., 4.])
    result = fit_localization_profiled(
        initial, ports, precision, lambda _state: True, max_iterations=24
    )
    assert all(right < left for left, right in zip(
        result.objectives, result.objectives[1:], strict=False
    ))
    assert result.associations == (0, 1)
    shifts = effective_shifts(result.mean)
    rank_one = effective_shift_precision(precision[2], precision[5:])
    # The unused catalogue coordinate remains in the correlated prior.  Its
    # conditional MAP need not be zero when selected effective shifts move.
    assert abs((rank_one @ shifts)[2]) < 1e-5
    assert abs(shifts[2] - effective_shifts(initial)[2]) > 1.
    assert np.isfinite(result.mean).all()


def test_affine_gaussian_fit_matches_original_coordinate_optimizer() -> None:
    ports = (
        _LinearPort(("a",), np.array([4.]), 3, 0),
        _LinearPort(("b",), np.array([-1.]), 3, 1),
    )
    initial = np.array([-3., 2., .6, 0., 0., -.4, .2, 5.])
    precision = np.array([.1, .1, 1., .5, .5, 4., 4., 4.])
    original = fit_localization_fast(initial, ports, precision, lambda _state: True)
    profiled = fit_localization_profiled(initial, ports, precision, lambda _state: True)
    assert original.converged and profiled.converged
    np.testing.assert_allclose(profiled.mean, original.mean, atol=1e-11)
    assert profiled.objectives[-1] == pytest.approx(original.objectives[-1], abs=1e-12)


def test_selected_score_and_prediction_must_match_association_pass() -> None:
    class WrongScore(_LinearPort):
        def score_all(self, state):
            return np.array([
                _LinearPort.score_selected(self, state, 0), self.background
            ])

        def score_selected(self, state, index):
            return super().score_selected(state, index) + 1.

    wrong = WrongScore(("a",), np.array([0.]), 1, 0)
    with pytest.raises(ValueError, match="selected physical score"):
        fit_localization_profiled(
            np.zeros(6), (wrong,), np.ones(6), lambda _state: True
        )

    class Ineligible(_LinearPort):
        def predict_selected(self, state, index):
            prediction = super().predict_selected(state, index)
            return Prediction(
                prediction.mean, prediction.jacobian, prediction.covariance, eligible=False
            )

    ineligible = Ineligible(("b",), np.array([0.]), 1, 0)
    with pytest.raises(ValueError, match="ineligible"):
        fit_localization_profiled(
            np.zeros(6), (ineligible,), np.ones(6), lambda _state: True
        )


def test_student_t_outlier_and_ill_conditioned_drift_remain_bounded() -> None:
    ports = tuple(
        _LinearPort((str(i),), np.array([value]), 1, 0, noise=1., nu=4.)
        for i, value in enumerate((0., 0., 100.))
    )
    result = fit_localization_profiled(
        np.zeros(6), ports, np.array([1., 1., 1., 0., 0., 4.]),
        lambda _state: True, degrees_of_freedom=4., max_iterations=12,
    )
    assert np.isfinite(result.mean).all()
    assert abs(result.mean[0] + result.mean[3] + 2 * result.mean[4]) < 1.


def test_invalid_unconstrained_clock_epoch_gauge_is_rejected() -> None:
    with pytest.raises(ValueError, match="gauge"):
        effective_shift_precision(0., np.zeros(2))
