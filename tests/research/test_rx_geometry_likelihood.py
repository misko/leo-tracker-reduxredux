import numpy as np
import pytest

from tools.rx_geometry_likelihood import (
    paired_log_likelihood,
    periodic_signal_ratio,
    update_score,
)

PERIOD = 227_000.0


def test_periodic_density_integrates_to_one() -> None:
    grid = np.linspace(-PERIOD / 2, PERIOD / 2, 200_001)
    density = periodic_signal_ratio(np.array([0.0]), grid, PERIOD, 20_000.0) / PERIOD
    assert np.trapezoid(density, grid) == pytest.approx(1.0, abs=2e-12)


def test_periodic_density_is_alias_invariant_and_empty_set_is_zero() -> None:
    frequencies = np.array([-91_000.0, 4_000.0, 113_000.0])
    expected = periodic_signal_ratio(frequencies, np.array([2_000.0, 8_000.0]), PERIOD, 3_000.0)
    shifted = periodic_signal_ratio(
        frequencies + 3 * PERIOD,
        np.array([2_000.0, 8_000.0]) - 2 * PERIOD,
        PERIOD,
        3_000.0,
    )
    np.testing.assert_allclose(shifted, expected, rtol=1e-14)
    np.testing.assert_array_equal(
        periodic_signal_ratio([], np.array([1.0, 2.0]), PERIOD, 1_000.0), [0.0, 0.0]
    )


def test_candidate_permutation_does_not_change_signal_sum() -> None:
    candidates = np.array([-20_000.0, 30.0, 45_000.0, 100.0])
    predicted = np.array([-100.0, 20_000.0])
    expected = periodic_signal_ratio(candidates, predicted, PERIOD, 2_000.0)
    actual = periodic_signal_ratio(candidates[[2, 0, 3, 1]], predicted, PERIOD, 2_000.0)
    np.testing.assert_allclose(actual, expected, rtol=1e-15)


def test_empty_candidate_set_has_missed_detection_likelihood() -> None:
    result = paired_log_likelihood(
        np.zeros((1, 1, 2)),
        np.zeros((1, 2), dtype=int),
        np.zeros((1, 1, 2)),
        np.ones((1, 1), dtype=bool),
        np.array([0.4, 0.7]),
        PERIOD,
        latent_sd=0.0,
    )
    assert result[0, 0] == pytest.approx(-1.1 + 2 * np.log(0.5))


def test_signal_sum_is_divided_by_receiver_clutter_intensity() -> None:
    result = paired_log_likelihood(
        np.array([[[4.0, 0.0]]]),
        np.array([[1, 0]]),
        np.zeros((1, 1, 2)),
        np.ones((1, 1), dtype=bool),
        np.array([2.0, 0.5]),
        PERIOD,
        latent_sd=0.0,
    )
    clutter = -2.5 + np.log(2.0 / PERIOD)
    expected_mixtures = np.log(0.5 + 0.5 * (4.0 / 2.0)) + np.log(0.5)
    assert result[0, 0] == pytest.approx(clutter + expected_mixtures)


def test_shared_rx_intercept_differs_from_independent_marginal_integration() -> None:
    sums = np.full((1, 1, 2), 12.0)
    counts = np.ones((1, 2), dtype=int)
    logits = np.zeros((1, 1, 2))
    visible = np.ones((1, 1), dtype=bool)
    rates = np.array([0.3, 0.3])
    shared = paired_log_likelihood(sums, counts, logits, visible, rates, PERIOD)[0, 0]
    first = paired_log_likelihood(sums[:, :, :].copy(), counts, logits, visible, rates, PERIOD)
    # Directly integrate each receiver by making the other receiver clutter-only.
    one_visible = np.array([[True]])
    rx0 = paired_log_likelihood(
        np.stack([sums[..., 0], np.zeros_like(sums[..., 1])], axis=-1),
        counts,
        np.stack([logits[..., 0], np.full_like(logits[..., 1], -1e6)], axis=-1),
        one_visible,
        rates,
        PERIOD,
    )[0, 0]
    # Remove the other receiver's constant clutter/missed-detection contribution.
    clutter_other = -rates[1] + np.log(rates[1] / PERIOD)
    marginal_rx0 = rx0 - clutter_other
    independent = 2 * marginal_rx0 + 2 * clutter_other
    assert first[0, 0] == shared
    assert shared != pytest.approx(independent)


def test_log_domain_prior_can_revive_tiny_finite_component() -> None:
    result = update_score(
        np.array([0.0, -2_000.0]),
        np.array([[0.0, 2_100.0]]),
        np.array([True]),
        np.array([False]),
    )
    assert result.reception_log_posterior[1] == pytest.approx(0.0)
    assert result.reception_log_posterior[0] == pytest.approx(-100.0)


def test_sequential_held_scores_sum_to_batch_conditional_evidence() -> None:
    prior = np.log([0.6, 0.4])
    likelihood = np.log([[0.5, 0.9], [0.8, 0.2], [0.25, 0.75]])
    result = update_score(prior, likelihood, [True, False, False], [False, True, True])
    reception_joint = prior + likelihood[0]
    reception_evidence = np.logaddexp.reduce(reception_joint)
    batch = np.logaddexp.reduce(reception_joint + likelihood[1] + likelihood[2])
    assert result.log_evidence == pytest.approx(batch - reception_evidence)
    assert result.held_window_log_scores.sum() == pytest.approx(result.log_evidence)
    assert np.logaddexp.reduce(result.held_log_posterior) == pytest.approx(0.0)
