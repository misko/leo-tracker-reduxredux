import itertools

import numpy as np
import pytest
from scipy.special import logsumexp

from tools.rx_presence_filter import forward_score, initial_log_prior, transition


def test_transition_has_exact_semigroup_for_arbitrary_gaps() -> None:
    prior = np.log([0.7, 0.3])
    first = np.exp(transition(prior, 0.37, 0.6, 2.4))
    second = np.exp(transition(prior, 8.91, 0.6, 2.4))
    combined = np.exp(transition(prior, 9.28, 0.6, 2.4))
    np.testing.assert_allclose(first @ second, combined, atol=2e-15)
    np.testing.assert_allclose(combined.sum(axis=1), 1.0, atol=2e-15)


def test_zero_gap_is_exact_identity() -> None:
    actual = transition(np.log([0.2, 0.8]), 0.0, 0.4, 3.0)
    expected = np.full((3, 3), -np.inf)
    np.fill_diagonal(expected, 0.0)
    np.testing.assert_array_equal(actual, expected)


def test_absence_remains_possible_with_all_catalogue_mass_retained() -> None:
    # One candidate has conditional retained mass one; occupancy independently
    # reserves nonzero probability for physical target absence.
    prior = initial_log_prior(np.array([0.0]), occupancy=0.75)
    np.testing.assert_allclose(np.exp(prior), [0.25, 0.75])


def test_tiny_finite_candidate_prior_can_be_revived_by_emission() -> None:
    result = forward_score(
        np.array([0.0, -2_000.0]),
        np.array([[0.0, 0.0, 2_100.0]]),
        np.array([0.0]),
        np.array([True]),
        np.array([False]),
        occupancy=0.5,
        tau=10.0,
    )
    assert result.state_log_posteriors[0, 2] == pytest.approx(0.0)
    assert result.state_log_posteriors[0, 1] == pytest.approx(-100.0)


def test_forward_scores_match_brute_force_path_enumeration() -> None:
    candidate = np.log([0.65, 0.35])
    times = np.array([0.0, 0.8, 3.1])
    emissions = np.log([[0.8, 0.2, 0.4], [0.1, 0.9, 0.3], [0.7, 0.25, 0.6]])
    result = forward_score(
        candidate, emissions, times, [True, True, False], [False, False, True], 0.55, 1.7
    )
    initial = initial_log_prior(candidate, 0.55)
    transitions = [transition(candidate, gap, 0.55, 1.7) for gap in np.diff(times)]
    prefix_evidence = []
    for end in range(len(times)):
        paths = []
        for states in itertools.product(range(3), repeat=end + 1):
            value = initial[states[0]] + emissions[0, states[0]]
            for index in range(1, end + 1):
                value += transitions[index - 1][states[index - 1], states[index]]
                value += emissions[index, states[index]]
            paths.append(value)
        prefix_evidence.append(logsumexp(paths))
    expected_scores = np.diff(np.r_[0.0, prefix_evidence])
    np.testing.assert_allclose(result.window_log_scores, expected_scores, atol=1e-14)


def test_held_prefix_is_scored_before_each_update() -> None:
    result = forward_score(
        np.log([0.5, 0.5]),
        np.log([[1.0, 1.0, 1.0], [0.2, 0.9, 0.1], [0.7, 0.1, 0.8]]),
        [0.0, 1.0, 2.0],
        [True, False, False],
        [False, True, True],
        occupancy=0.6,
        tau=2.0,
    )
    assert result.window_log_scores[0] == pytest.approx(0.0)
    # The third score uses the second held posterior, not the reception posterior again.
    reception = result.reception_log_posterior
    propagated = logsumexp(
        reception[:, None] + transition(np.log([0.5, 0.5]), 1.0, 0.6, 2.0), axis=0
    )
    second_score = logsumexp(propagated + np.log([0.2, 0.9, 0.1]))
    second_posterior = propagated + np.log([0.2, 0.9, 0.1]) - second_score
    third_predictive = logsumexp(
        second_posterior[:, None] + transition(np.log([0.5, 0.5]), 1.0, 0.6, 2.0), axis=0
    )
    expected_third = logsumexp(third_predictive + np.log([0.7, 0.1, 0.8]))
    assert result.window_log_scores[2] == pytest.approx(expected_third)
