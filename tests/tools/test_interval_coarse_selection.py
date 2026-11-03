"""Prove selector mechanics against full selection under supplied valid intervals."""

import numpy as np
import pytest
from interval_coarse_selection import retain, select


def check(truth, screen, error, residuals, count=3, epoch_sep=3, cfo_sep=2):
    expected = retain(truth, residuals, count, epoch_sep, cfo_sep)
    seen = []

    def oracle(columns):
        seen.extend(columns)
        return truth[:, columns]

    actual = select(screen, error, residuals, count, epoch_sep, cfo_sep, oracle)
    assert actual['retained'] == expected
    assert len(seen) == len(set(seen))
    return actual


def test_random_intervals_and_suppression_match_complete_selection():
    from leo.analysis.starlink.acquisition import _local_peak_indexes, _retain_separated

    rng = np.random.default_rng(1729)
    for _ in range(150):
        truth = rng.integers(0, 20, size=(3, 37)).astype(float)
        error = rng.uniform(0, 3, truth.shape)
        screen = truth + rng.uniform(-1, 1, truth.shape) * error
        candidates = [(float(scores[e]), e, residual)
                      for residual, scores in zip((-2, 0, 2), truth, strict=True)
                      for e in _local_peak_indexes(scores)]
        candidates.sort(key=lambda x: (x[0], -abs(x[2]), -x[1]), reverse=True)
        assert retain(truth, [-2, 0, 2], 3, 3, 2) == _retain_separated(
            candidates, 3, 3, 2, 37)
        check(truth, screen, error, [-2, 0, 2])


@pytest.mark.parametrize('truth', [
    [[0, 1, 1, 1, 0], [0, 1, 1, 1, 0]],
    [[5, 0, 4, 0, 5], [5, 0, 4, 0, 5]],
    [[0, 0, 0, 0, 0], [0, 0, 0, 0, 0]],
    [[4], [4]],
    [[0], [0]],
    [[3, 0, 4, 0, 5, 0, 6, 0, 7], [0, 0, 0, 0, 0, 0, 0, 0, 0]],
])
def test_ties_plateaus_edges_and_suppression_cascades(truth):
    truth = np.asarray(truth, float)
    check(truth, truth.copy(), 0., [-1, 1])


def test_clear_peaks_need_only_sparse_exact_columns():
    truth = np.zeros((2, 1000))
    truth[0, [50, 300, 800]] = [4, 3, 2]
    result = check(truth, truth + .00001, .00002, [-1, 1])
    assert result['fallback'] is None
    assert result['exact_columns'] == 9


def test_observed_bad_bound_falls_back_to_full_grid():
    truth = np.zeros((2, 20))
    truth[0, 5] = 5
    screen = truth.copy()
    screen[0, 5] = 10
    result = check(truth, screen, .01, [-1, 1], count=1)
    assert result['fallback'] == 'sampled bound violation'
    assert result['exact_columns'] == 20


@pytest.mark.parametrize('bad', [-1., np.nan, np.inf])
def test_invalid_bounds_rejected(bad):
    with pytest.raises(ValueError):
        select(np.zeros((2, 10)), bad, [-1, 1], 2, 2, 1, lambda _: None)
