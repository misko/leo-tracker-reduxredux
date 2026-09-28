import math

import numpy as np
import pytest
from scipy.special import logsumexp

from tools.rx_empirical_signal import paired_relative_log_likelihood
from tools.rx_geometry_likelihood import paired_log_likelihood


def _poisson_count_grid(counts, lambdas):
    result = np.full((len(counts), 2, 2), -np.inf)
    for window, (left, right) in enumerate(counts):
        for signal0 in (0, 1):
            for signal1 in (0, 1):
                shifted = (left - signal0, right - signal1)
                if min(shifted) < 0:
                    continue
                result[window, signal0, signal1] = sum(
                    -rate + count * np.log(rate) - math.lgamma(count + 1)
                    for count, rate in zip(shifted, lambdas, strict=True)
                )
    return result


def test_kernel_matches_direct_four_pattern_sum() -> None:
    counts = np.array([[2, 1]])
    count_logs = np.log(np.array([[[0.20, 0.15], [0.10, 0.05]]]))
    ratios = np.array([[[1.8, 0.7]]])
    logits = np.array([[[0.4, -0.2]]])
    actual = paired_relative_log_likelihood(
        count_logs, ratios, counts, logits, [[True]], latent_sd=0.0
    )[0, 0]
    probabilities = 1 / (1 + np.exp(-logits[0, 0]))
    total = 0.0
    for signal0 in (0, 1):
        for signal1 in (0, 1):
            weight = (probabilities[0] if signal0 else 1 - probabilities[0]) * (
                probabilities[1] if signal1 else 1 - probabilities[1]
            )
            assignment = (ratios[0, 0, 0] / 2 if signal0 else 1.0) * (
                ratios[0, 0, 1] if signal1 else 1.0
            )
            total += (
                weight * np.exp(count_logs[0, signal0, signal1] - count_logs[0, 0, 0]) * assignment
            )
    assert actual == pytest.approx(np.log(total))


def test_relative_model_normalizes_with_geometric_count_tail() -> None:
    mean = np.array([0.8, 1.3])
    logits = np.array([[[0.2, -0.5]]])
    mass = 0.0
    for left in range(80):
        for right in range(80):
            counts = np.array([[left, right]])
            logs = np.full((1, 2, 2), -np.inf)
            for signal0 in (0, 1):
                for signal1 in (0, 1):
                    shifted = (left - signal0, right - signal1)
                    if min(shifted) >= 0:
                        logs[0, signal0, signal1] = sum(
                            count * np.log(rate) - (count + 1) * np.log1p(rate)
                            for count, rate in zip(shifted, mean, strict=True)
                        )
            ratios = np.array([[[float(left), float(right)]]])
            relative = paired_relative_log_likelihood(
                logs, ratios, counts, logits, [[True]], latent_sd=0.7
            )[0, 0]
            mass += np.exp(logs[0, 0, 0] + relative)
    assert mass == pytest.approx(1.0, abs=2e-12)


def test_zero_count_forces_no_signal_for_that_receiver() -> None:
    counts = np.array([[0, 1]])
    logs = _poisson_count_grid(counts, np.array([0.8, 1.1]))
    first = paired_relative_log_likelihood(
        logs, np.array([[[0.0, 1.5]]]), counts, np.array([[[0.7, 0.0]]]), [[True]]
    )
    second = paired_relative_log_likelihood(
        logs, np.array([[[1_000.0, 1.5]]]), counts, np.array([[[0.7, 0.0]]]), [[True]]
    )
    np.testing.assert_array_equal(first, second)


def test_invisible_component_is_background_ratio_one() -> None:
    counts = np.array([[1, 2]])
    logs = _poisson_count_grid(counts, np.array([1.0, 1.0]))
    actual = paired_relative_log_likelihood(
        logs,
        np.array([[[100.0, 200.0]]]),
        counts,
        np.array([[[10.0, 10.0]]]),
        [[False]],
    )
    np.testing.assert_array_equal(actual, [[0.0]])


def test_poisson_background_recovers_original_paired_kernel_ratio() -> None:
    counts = np.array([[2, 1], [0, 3]])
    lambdas = np.array([0.8, 1.4])
    signal = np.array([[[2.4, 0.7]], [[0.0, 3.2]]])
    logits = np.array([[[0.2, -0.4]], [[1.0, 0.3]]])
    visible = np.ones((2, 1), dtype=bool)
    count_logs = _poisson_count_grid(counts, lambdas)
    relative = paired_relative_log_likelihood(
        count_logs, signal, counts, logits, visible, latent_sd=1.0
    )
    period = 227_000.0
    original = paired_log_likelihood(
        signal, counts, logits, visible, lambdas, period, latent_sd=1.0
    )
    background = np.sum(-lambdas + counts * np.log(lambdas / period), axis=1)
    np.testing.assert_allclose(relative, original - background[:, None], atol=2e-14)


def test_candidate_component_axis_is_vectorized() -> None:
    counts = np.array([[1, 1]])
    logs = _poisson_count_grid(counts, np.array([1.0, 1.0]))
    result = paired_relative_log_likelihood(
        logs,
        np.array([[[1.0, 2.0], [3.0, 4.0]]]),
        counts,
        np.zeros((1, 2, 2)),
        [[True, True]],
    )
    assert result.shape == (1, 2)
    assert logsumexp(result) > result.max()


@pytest.mark.parametrize("invalid", [np.inf, np.nan])
def test_nonfinite_counts_are_rejected(invalid) -> None:
    with pytest.raises(ValueError, match="counts must be nonnegative integers"):
        paired_relative_log_likelihood(
            np.zeros((1, 2, 2)),
            np.ones((1, 1, 2)),
            np.array([[invalid, 1.0]]),
            np.zeros((1, 1, 2)),
            [[True]],
        )
