import numpy as np
import pytest
from scipy.special import logsumexp

from tools.rx_geometry_score_decomposition import (
    decompose_sequence,
    paired_count_log_likelihood,
)

PERIOD = 227_000.0


def test_paired_count_pmf_normalizes() -> None:
    grid = np.array([[left, right] for left in range(25) for right in range(25)])
    logits = np.broadcast_to(np.array([[[0.3, -0.4]]]), (len(grid), 1, 2))
    logpmf = paired_count_log_likelihood(
        grid,
        logits,
        np.ones((len(grid), 1), dtype=bool),
        np.array([1.2, 1.8]),
        PERIOD,
        quadrature_order=15,
    )
    assert np.exp(logsumexp(logpmf[:, 0])) == pytest.approx(1.0, abs=2e-12)


def test_decomposition_parts_sum_to_full_score() -> None:
    result = decompose_sequence(
        np.log([0.7, 0.3]),
        np.log([[0.8, 0.2], [0.1, 0.9], [0.6, 0.3]]),
        np.log([[0.5, 0.5], [0.7, 0.4], [0.2, 0.8]]),
        [True, False, False],
        [False, True, True],
    )
    np.testing.assert_allclose(
        result.full_window_log_scores,
        result.count_window_log_scores + result.conditional_frequency_window_log_scores,
    )
    assert result.full_log_evidence == pytest.approx(
        result.count_log_evidence + result.conditional_frequency_log_evidence
    )


def test_count_score_uses_full_evidence_mixture_history() -> None:
    prior = np.log([0.5, 0.5])
    full = np.log([[0.99, 0.01], [0.99, 0.01]])
    count = np.log([[0.01, 0.99], [0.01, 0.99]])
    result = decompose_sequence(prior, full, count, [False, False], [True, True])

    initial = prior - logsumexp(prior)
    expected_first = logsumexp(initial + count[0])
    after_full = initial + full[0] - logsumexp(initial + full[0])
    expected_second = logsumexp(after_full + count[1])
    count_filtered = initial + count[0] - logsumexp(initial + count[0])
    wrong_second = logsumexp(count_filtered + count[1])

    np.testing.assert_allclose(result.count_window_log_scores, [expected_first, expected_second])
    assert result.count_window_log_scores[1] != pytest.approx(wrong_second)
