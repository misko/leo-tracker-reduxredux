from __future__ import annotations

from math import exp, log, pi

import numpy as np
import pytest

from leo.analysis.gaussian_sum_location import (
    Candidate,
    FilterConfig,
    FilterState,
    GaussianComponent,
    ObservationFactor,
    Prediction,
    gaussian_logpdf,
    marginalize_local_covariance,
    update_filter,
)


def _state(mean: np.ndarray, covariance: np.ndarray) -> FilterState:
    return FilterState((GaussianComponent(1.0, mean, covariance),))


def _linear(label: str, matrix: np.ndarray, covariance: np.ndarray) -> Candidate:
    return Candidate(
        label,
        0.8,
        lambda mean: Prediction(matrix @ mean, matrix, covariance),
    )


def test_exact_linear_update_and_proper_predictive_density() -> None:
    state = _state(np.array([0.0]), np.array([[4.0]]))
    candidate = _linear("sat-1", np.array([[1.0]]), np.array([[1.0]]))
    factor = ObservationFactor(("track-1",), np.array([2.0]), (candidate,), 0.2, -10.0)

    result = update_filter(state, factor, FilterConfig(max_components=2))

    signal_log = log(0.8) - 0.5 * (log(2 * pi * 5.0) + 4.0 / 5.0)
    expected_log = np.logaddexp(signal_log, log(0.2) - 10.0)
    assert result.predictive_log_density == pytest.approx(expected_log)
    signal = next(c for c in result.state.components if c.identity_history == ("sat-1",))
    assert signal.mean == pytest.approx([1.6])
    np.testing.assert_allclose(signal.covariance, [[0.8]])
    assert result.association_probabilities["sat-1"] == pytest.approx(
        exp(signal_log - expected_log)
    )
    assert result.background_probability == pytest.approx(exp(log(0.2) - 10.0 - expected_log))


def test_global_normalization_across_parents_and_candidates() -> None:
    state = FilterState(
        (
            GaussianComponent(0.25, np.array([-2.0]), np.array([[1.0]]), ("west",)),
            GaussianComponent(0.75, np.array([2.0]), np.array([[1.0]]), ("east",)),
        )
    )
    candidates = (
        Candidate("a", 0.4, lambda x: Prediction(x, np.eye(1), np.eye(1))),
        Candidate("b", 0.5, lambda x: Prediction(x + 1.0, np.eye(1), np.eye(1))),
    )
    factor = ObservationFactor(("x",), np.array([0.0]), candidates, 0.1, -3.0)

    result = update_filter(state, factor, FilterConfig(max_components=6))

    assert sum(c.weight for c in result.state.components) == pytest.approx(1.0)
    assert sum(
        result.association_probabilities.values()
    ) + result.background_probability == pytest.approx(1.0)
    assert len(result.state.components) == 6


def test_shared_nuisance_cross_covariance_is_conditioned() -> None:
    # Observation x + drift updates both coordinates and retains their correlation.
    state = _state(np.zeros(2), np.diag([4.0, 9.0]))
    h = np.array([[1.0, 1.0]])
    candidate = Candidate("sat", 1.0, lambda x: Prediction(h @ x, h, np.array([[1.0]])))
    factor = ObservationFactor(("joint",), np.array([2.0]), (candidate,), 0.0, -2.0)

    result = update_filter(state, factor, FilterConfig(max_components=1))
    component = result.state.components[0]

    assert component.mean == pytest.approx([4.0 / 14.0 * 2.0, 9.0 / 14.0 * 2.0])
    assert component.covariance[0, 1] == pytest.approx(-36.0 / 14.0)
    np.linalg.cholesky(component.covariance)


def test_sequential_linear_updates_match_batch_conditioning() -> None:
    initial = _state(np.array([0.0]), np.array([[3.0]]))
    candidate = Candidate("sat", 1.0, lambda mean: Prediction(mean, np.eye(1), np.array([[2.0]])))
    first = update_filter(
        initial,
        ObservationFactor(("a",), np.array([1.0]), (candidate,), 0.0, -1.0),
        FilterConfig(max_components=1),
    )
    second = update_filter(
        first.state,
        ObservationFactor(("b",), np.array([4.0]), (candidate,), 0.0, -1.0),
        FilterConfig(max_components=1),
    )

    expected_variance = 1.0 / (1.0 / 3.0 + 2.0 / 2.0)
    expected_mean = expected_variance * (1.0 / 2.0 + 4.0 / 2.0)
    assert second.state.components[0].mean == pytest.approx([expected_mean])
    np.testing.assert_allclose(second.state.components[0].covariance, [[expected_variance]])
    assert second.state.components[0].identity_history == ("sat", "sat")


def test_pruning_reports_full_posterior_mass_and_greedy_uses_same_scores() -> None:
    state = _state(np.array([0.0]), np.array([[1.0]]))
    candidates = (
        Candidate("near", 0.45, lambda x: Prediction(x, np.eye(1), np.eye(1))),
        Candidate("far", 0.45, lambda x: Prediction(x + 5.0, np.eye(1), np.eye(1))),
    )
    factor = ObservationFactor(("one",), np.array([0.0]), candidates, 0.1, -4.0)
    full = update_filter(state, factor, FilterConfig(max_components=3))
    greedy = update_filter(state, factor, FilterConfig(max_components=3, greedy=True))

    winner = max(full.state.components, key=lambda component: component.weight)
    assert greedy.state.components[0].identity_history == winner.identity_history
    assert greedy.predictive_log_density == pytest.approx(full.predictive_log_density)
    assert greedy.retained_pre_normalization_mass == pytest.approx(winner.weight)
    assert greedy.discarded_pre_normalization_mass == pytest.approx(1.0 - winner.weight)


def test_duplicate_and_over_budget_factors_fail_explicitly() -> None:
    state = FilterState(
        (GaussianComponent(1.0, np.zeros(1), np.eye(1)),), consumed_observation_ids=("used",)
    )
    candidate = _linear("sat", np.eye(1), np.eye(1))
    duplicate = ObservationFactor(("used",), np.zeros(1), (candidate,), 0.2, -1.0)
    with pytest.raises(ValueError, match="already consumed"):
        update_filter(state, duplicate, FilterConfig(max_components=2))

    fresh = ObservationFactor(("fresh",), np.zeros(1), (candidate,), 0.2, -1.0)
    with pytest.raises(ValueError, match="child evaluations"):
        update_filter(state, fresh, FilterConfig(max_components=2, max_child_work=1))


def test_state_dependent_priors_are_local_and_validated_per_parent() -> None:
    state = _state(np.array([1.0]), np.eye(1))
    candidate = Candidate(
        "sat",
        lambda mean: 0.7 if mean[0] > 0 else 0.2,
        lambda mean: Prediction(mean, np.eye(1), np.eye(1)),
    )
    factor = ObservationFactor(("track",), np.ones(1), (candidate,), lambda _: 0.3, -2.0)
    result = update_filter(state, factor, FilterConfig(max_components=2))
    assert "local_prior_approximation" in result.flags

    invalid = ObservationFactor(("other",), np.ones(1), (candidate,), 0.4, -2.0)
    with pytest.raises(ValueError, match="sum to one"):
        update_filter(state, invalid, FilterConfig(max_components=2))


def test_local_covariance_marginalization_and_extreme_log_density() -> None:
    covariance = marginalize_local_covariance(
        np.diag([1.0, 2.0]), np.array([[1.0], [2.0]]), np.array([[3.0]])
    )
    np.testing.assert_allclose(covariance, [[4.0, 6.0], [6.0, 14.0]])
    np.testing.assert_allclose(
        marginalize_local_covariance(np.zeros((2, 2)), np.eye(2), np.eye(2)), np.eye(2)
    )
    assert np.isfinite(gaussian_logpdf(np.array([1e100]), np.array([[1e200]])))


def test_internal_innovation_roundoff_is_symmetrized_without_weakening_inputs() -> None:
    times = np.array(
        [0.0, 5.11643988, 15.43916897, 20.63783344,
         27.27784396, 36.38170975, 43.82583451, 51.36313777]
    )
    lag = np.abs(times[:, None] - times[None, :])
    state_covariance = 100.0**2 * np.eye(8) + 100.0**2 * np.exp(-lag / 0.5)
    contrasts = np.zeros((7, 8))
    for row in range(7):
        contrasts[row, : row + 1] = 1.0 / np.sqrt((row + 1) * (row + 2))
        contrasts[row, row + 1] = -(row + 1) / np.sqrt((row + 1) * (row + 2))
    state = _state(np.zeros(8), state_covariance)
    candidate = Candidate(
        "roundoff", 1.0, lambda mean: Prediction(contrasts @ mean, contrasts, np.eye(7))
    )
    factor = ObservationFactor(("roundoff",), np.zeros(7), (candidate,), 0.0, -1.0)
    result = update_filter(state, factor, FilterConfig(max_components=1))
    assert result.status == "updated"

    with pytest.raises(ValueError, match="measurement covariance must be symmetric"):
        marginalize_local_covariance(
            np.array([[2.0, 0.1], [0.2, 2.0]]), np.eye(2), np.eye(2)
        )


def test_arrays_are_copied_and_immutable_for_deterministic_history() -> None:
    mean = np.array([0.0])
    component = GaussianComponent(1.0, mean, np.eye(1))
    mean[0] = 10.0
    assert component.mean[0] == 0.0
    with pytest.raises(ValueError):
        component.mean[0] = 3.0


def test_exactly_underflowed_children_are_not_materialized() -> None:
    state = _state(np.array([0.0]), np.eye(1))
    candidates = (
        Candidate("near", 0.5, lambda x: Prediction(x, np.eye(1), np.eye(1))),
        Candidate("astronomical", 0.5, lambda x: Prediction(x + 1e100, np.eye(1), np.eye(1))),
    )
    factor = ObservationFactor(("extreme",), np.zeros(1), candidates, 0.0, -1.0)
    result = update_filter(state, factor, FilterConfig(max_components=2))
    assert len(result.state.components) == 1
    assert result.state.components[0].identity_history == ("near",)
