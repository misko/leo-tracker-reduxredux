import itertools
import numpy as np
from common import group_map, distinct_peak_rows, ALIAS_HZ


def test_period_copies_not_independent_peaks():
    rows, copies = distinct_peak_rows(np.arange(4), np.array([1., 1.+ALIAS_HZ, 2., 2.001]))
    assert list(rows) == [0, 2, 3]
    assert copies == {1: 0}


def test_simultaneous_and_exclusive():
    pairs, score = group_map(np.array([[4., 1.], [2., 5.], [3., 2.]]))
    assert set(pairs) == {(0, 0), (1, 1)}
    assert score == 9


def test_negative_evidence_is_clutter():
    assert group_map(np.array([[-1., -np.inf]])) == ([], 0.)


def test_dp_matches_bruteforce():
    rng = np.random.default_rng(19)
    for _ in range(20):
        gain = rng.normal(size=(4, 3))
        best = 0.
        for labels in itertools.product(range(-1, 3), repeat=4):
            selected = [s for s in labels if s >= 0]
            if len(set(selected)) != len(selected):
                continue
            best = max(best, sum(gain[r, s] for r, s in enumerate(labels) if s >= 0))
        pairs, score = group_map(gain)
        assert np.isclose(score, best)
        assert len({r for r, _ in pairs}) == len(pairs)
        assert len({s for _, s in pairs}) == len(pairs)
