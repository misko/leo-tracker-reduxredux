from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np
import pytest

from leo.analysis.gaussian_sum_location import Prediction
from leo.analysis.localization_soft import _scatter_normal_contribution, fit_joint_soft
from leo.analysis.robust_likelihood import student_t_logpdf


@dataclass
class _Port:
    observation_ids: tuple[str, ...]
    observation: np.ndarray
    predictions: tuple[Prediction, ...]
    log_priors: np.ndarray
    background_log_joint: float = -np.inf
    priors_piecewise_constant: bool = True

    @property
    def candidate_count(self) -> int:
        return len(self.predictions)

    def score_all(self, state: np.ndarray) -> np.ndarray:
        values = []
        for prior, prediction in zip(self.log_priors, self.predictions, strict=True):
            mean = prediction.jacobian @ state
            values.append(
                prior
                + student_t_logpdf(
                    self.observation - mean, prediction.covariance, 4.0
                )
            )
        return np.array([*values, self.background_log_joint])

    def predict_selected(self, state: np.ndarray, index: int) -> Prediction:
        prediction = self.predictions[index]
        return Prediction(
            prediction.jacobian @ state,
            prediction.jacobian,
            prediction.covariance,
            prediction.eligible,
        )


def _prediction(matrix, variance=1.0, *, eligible=True):
    matrix = np.asarray(matrix, dtype=float).reshape(1, -1)
    return Prediction(np.zeros(1), matrix, np.array([[variance]]), eligible)


def test_soft_ambiguous_branches_recover_symmetric_stationary_point_and_probabilities() -> None:
    port = _Port(
        ("physical",),
        np.array([2.0]),
        (_prediction([1.0]), _prediction([-1.0])),
        np.log(np.array([0.5, 0.5])),
        -100.0,
    )
    result = fit_joint_soft(
        np.array([0.0]), (port,), np.array([0.1]), lambda _state: True,
        max_active_branches_per_factor=None,
    )
    assert result.converged
    assert result.mean[0] == pytest.approx(0.0, abs=1e-12)
    np.testing.assert_allclose(result.responsibilities[0][:2], [0.5, 0.5])
    assert result.responsibilities[0].sum() == pytest.approx(1.0)
    assert not result.proposal_is_approximate
    assert result.admissible_for_official_benchmark


def test_full_soft_objective_decreases_for_affine_factors() -> None:
    ports = (
        _Port(("a",), np.array([3.0]), (_prediction([1.0, 1.0]),), np.array([0.0])),
        _Port(("b",), np.array([1.0]), (_prediction([1.0, -1.0]),), np.array([0.0])),
    )
    result = fit_joint_soft(
        np.array([-4.0, 2.0]), ports, np.array([0.01, 0.01]), lambda _state: True,
        max_active_branches_per_factor=None,
    )
    assert result.converged
    assert all(right < left for left, right in zip(result.objectives, result.objectives[1:]))
    np.testing.assert_allclose(result.mean, [1.99, 0.995], atol=0.03)


def test_background_is_normalized_but_has_no_measurement_gradient() -> None:
    port = _Port(
        ("a",), np.array([5.0]), (_prediction([1.0]),), np.array([np.log(0.1)]), 0.0
    )
    result = fit_joint_soft(
        np.zeros(1), (port,), np.ones(1), lambda _state: True,
        max_active_branches_per_factor=None,
    )
    assert result.responsibilities[0][-1] > 0.5
    assert result.responsibilities[0].sum() == pytest.approx(1.0)


def test_working_set_fails_instead_of_renormalizing_omitted_mass() -> None:
    port = _Port(
        ("a",), np.array([0.0]),
        tuple(_prediction([1.0]) for _ in range(4)),
        np.log(np.full(4, 0.25)),
    )
    result = fit_joint_soft(
        np.zeros(1), (port,), np.ones(1), lambda _state: True,
        max_active_branches_per_factor=2, max_omitted_responsibility=0.1,
    )
    assert not result.converged
    assert result.reason == "working_set_mass_exceeded"
    assert not result.admissible_for_official_benchmark
    assert result.max_omitted_responsibility == pytest.approx(0.5)
    np.testing.assert_allclose(result.responsibilities[0][:4], np.full(4, 0.25))


def test_small_omitted_mass_is_reported_and_full_objective_accepts_steps() -> None:
    port = _Port(
        ("a",), np.array([2.0]),
        (_prediction([1.0]), _prediction([-1.0]), _prediction([0.5])),
        np.log(np.array([0.999, 0.0009, 0.0001])),
        -100.0,
    )
    result = fit_joint_soft(
        np.zeros(1), (port,), np.array([0.01]), lambda _state: True,
        max_active_branches_per_factor=1, max_omitted_responsibility=0.01,
    )
    assert result.proposal_is_approximate
    assert not result.admissible_for_official_benchmark
    assert 0.0 < result.max_omitted_responsibility <= 0.01
    assert all(right < left for left, right in zip(result.objectives, result.objectives[1:]))


def test_logsumexp_responsibilities_are_stable_for_extreme_log_scores() -> None:
    port = _Port(
        ("a",), np.array([0.0]),
        (_prediction([1.0]), _prediction([1.0])),
        np.array([-1000.0, 0.0]),
        -2000.0,
    )
    result = fit_joint_soft(
        np.zeros(1), (port,), np.ones(1), lambda _state: True,
        max_active_branches_per_factor=None,
    )
    assert result.responsibilities[0][1] == pytest.approx(1.0)
    assert result.responsibilities[0].sum() == pytest.approx(1.0)


def test_full_objective_rejects_proposal_across_state_dependent_score_boundary() -> None:
    class BoundaryPort(_Port):
        def score_all(self, state):
            values = super().score_all(state)
            if state[0] > 0.25:
                values[:-1] -= 100.0
            return values

    port = BoundaryPort(
        ("a",), np.array([3.0]), (_prediction([1.0]),), np.array([0.0]), -10.0
    )
    result = fit_joint_soft(
        np.zeros(1), (port,), np.zeros(1), lambda _state: True,
        max_iterations=1, max_active_branches_per_factor=None,
    )
    assert result.mean[0] <= 0.25
    assert result.accepted_step_norms
    assert result.objectives[-1] < result.objectives[0]


def test_duplicate_physical_observations_and_bad_scores_are_rejected() -> None:
    port = _Port(("same",), np.zeros(1), (_prediction([1.0]),), np.array([0.0]))
    with pytest.raises(ValueError, match="must not be reused"):
        fit_joint_soft(np.zeros(1), (port, port), np.ones(1), lambda _state: True)

    class BadPort(_Port):
        def score_all(self, state):
            return np.array([np.nan, 0.0])

    bad = BadPort(**port.__dict__)
    with pytest.raises(ValueError, match="invalid normalized log-joints"):
        fit_joint_soft(np.zeros(1), (bad,), np.ones(1), lambda _state: True)


def test_expired_deadline_returns_bounded_status_without_prediction_work() -> None:
    port = _Port(("a",), np.zeros(1), (_prediction([1.0]),), np.array([0.0]))
    result = fit_joint_soft(
        np.zeros(1), (port,), np.ones(1), lambda _state: True,
        deadline=time.monotonic() - 1.0,
    )
    assert not result.converged
    assert result.reason == "wall_budget"
    assert result.iterations == 0
    assert not result.responsibilities_at_mean
    assert result.responsibilities is None


def test_full_derivatives_are_default_and_required_for_official_admission() -> None:
    port = _Port(
        ("a",), np.zeros(1),
        tuple(_prediction([1.0]) for _ in range(12)),
        np.full(12, -np.log(12.0)),
    )
    result = fit_joint_soft(np.zeros(1), (port,), np.ones(1), lambda _state: True)
    assert not result.proposal_is_approximate
    assert result.admissible_for_official_benchmark


def test_unknown_smooth_prior_is_rejected_without_gradient_protocol() -> None:
    port = _Port(
        ("a",), np.zeros(1), (_prediction([1.0]),), np.array([0.0]),
        priors_piecewise_constant=False,
    )
    with pytest.raises(ValueError, match="priors_piecewise_constant"):
        fit_joint_soft(np.zeros(1), (port,), np.ones(1), lambda _state: True)


def test_sparse_scatter_matches_full_width_dense_normal_equations() -> None:
    rng = np.random.default_rng(82173)
    state_dimension = 29
    active = np.array([0, 1, 3, 7, 11, 18, 23, 28])
    lookup = np.full(state_dimension, -1, dtype=int)
    lookup[active] = np.arange(active.size)
    system = np.diag(rng.uniform(0.1, 2.0, active.size))
    gradient = rng.normal(size=active.size)
    expected_system = system.copy()
    expected_gradient = gradient.copy()

    for _ in range(17):
        rows = 4
        local_global = rng.choice(active, size=5, replace=False)
        jacobian = np.zeros((rows, state_dimension))
        jacobian[:, local_global] = rng.normal(size=(rows, local_global.size))
        raw = rng.normal(size=(rows, rows))
        covariance = raw @ raw.T + np.eye(rows) * 0.3
        residual = rng.normal(size=rows)
        weight = float(rng.uniform(0.01, 1.7))

        full_h = jacobian[:, active]
        expected_system += weight * full_h.T @ np.linalg.solve(covariance, full_h)
        expected_gradient += weight * full_h.T @ np.linalg.solve(covariance, residual)
        _scatter_normal_contribution(
            system, gradient, lookup, jacobian, covariance, residual, weight
        )

    np.testing.assert_allclose(system, expected_system, rtol=1e-12, atol=1e-12)
    np.testing.assert_allclose(gradient, expected_gradient, rtol=1e-12, atol=1e-12)


def test_bulk_and_prediction_fallback_have_identical_fit_outcomes() -> None:
    fallback = _Port(
        ("bulk",), np.array([2.5]),
        (_prediction([1.0, 0.5], 0.7), _prediction([-0.2, 1.0], 0.7)),
        np.log(np.array([0.7, 0.3])), -20.0,
    )

    class BulkPort:
        def __init__(self, wrapped):
            self.wrapped = wrapped
            self.observation_ids = wrapped.observation_ids
            self.observation = wrapped.observation
            self.candidate_count = wrapped.candidate_count
            self.priors_piecewise_constant = True
            self.bulk_calls = 0
            self.fallback_calls = 0

        def score_all(self, state):
            return self.wrapped.score_all(state)

        def predict_selected(self, state, index):
            self.fallback_calls += 1
            raise AssertionError("bulk-capable port must not construct Prediction objects")

        def linearize_candidates(self, state, indices):
            self.bulk_calls += 1
            indices = np.asarray(indices, dtype=np.int64)
            predictions = [self.wrapped.predict_selected(state, int(i)) for i in indices]
            return {
                "indices": indices,
                "means": np.stack([item.mean for item in predictions]),
                "jacobians": np.stack([item.jacobian for item in predictions]),
                "columns": np.tile(
                    np.arange(state.size, dtype=np.int64), (indices.size, 1)
                ),
                "covariance": predictions[0].covariance,
                "eligible": np.array([item.eligible for item in predictions], dtype=bool),
            }

    bulk = BulkPort(fallback)
    arguments = (np.array([-1.0, 1.5]), np.array([0.03, 0.05]), lambda _state: True)
    expected = fit_joint_soft(arguments[0], (fallback,), arguments[1], arguments[2])
    actual = fit_joint_soft(arguments[0], (bulk,), arguments[1], arguments[2])

    np.testing.assert_allclose(actual.mean, expected.mean, rtol=1e-12, atol=1e-12)
    np.testing.assert_allclose(actual.objectives, expected.objectives, rtol=1e-12, atol=1e-12)
    np.testing.assert_allclose(
        actual.accepted_step_norms, expected.accepted_step_norms, rtol=1e-12, atol=1e-12
    )
    assert actual.responsibilities is not None and expected.responsibilities is not None
    np.testing.assert_allclose(
        actual.responsibilities[0], expected.responsibilities[0], rtol=1e-12, atol=1e-12
    )
    assert (actual.converged, actual.iterations, actual.reason) == (
        expected.converged, expected.iterations, expected.reason
    )
    assert bulk.bulk_calls > 0
    assert bulk.fallback_calls == 0


def test_bulk_all_background_does_not_request_empty_linearization() -> None:
    class AllBackgroundBulkPort:
        observation_ids = ("background-only",)
        observation = np.zeros(1)
        candidate_count = 3
        priors_piecewise_constant = True

        def score_all(self, _state):
            return np.array([-np.inf, -np.inf, -np.inf, 0.0])

        def linearize_candidates(self, _state, _indices):
            raise AssertionError("empty candidate set must bypass bulk linearization")

        def predict_selected(self, _state, _index):
            raise AssertionError("all-background factor must not request a prediction")

    result = fit_joint_soft(
        np.zeros(1), (AllBackgroundBulkPort(),), np.ones(1), lambda _state: True
    )
    assert not result.converged
    assert result.reason == "all_background"
    assert result.responsibilities is not None
    np.testing.assert_array_equal(result.responsibilities[0], [0.0, 0.0, 0.0, 1.0])
