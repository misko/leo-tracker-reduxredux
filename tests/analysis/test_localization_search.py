import numpy as np
import pytest

from leo.analysis.localization_search import MemoizedPointScorer


def test_exact_reuse_keeps_order_duplicates_and_adjacent_float_distinct():
    calls = []

    def score(points):
        calls.append(points.copy())
        return points[:, 0]+points[:, 1]

    cached = MemoizedPointScorer(score)
    points = np.array([[1., 2.], [4., 3.], [1., 2.]])
    np.testing.assert_array_equal(cached(points), [3., 7., 3.])
    assert len(calls[0]) == 2
    next_points = np.array([[4., 3.], [np.nextafter(1., 2.), 2.]])
    np.testing.assert_array_equal(cached(next_points), score(next_points))
    assert cached.requested_points == 5 and cached.evaluated_points == 3


def test_cache_is_per_instance_and_output_is_not_mutable_state():
    first = MemoizedPointScorer(lambda x: x[:, 0])
    second = MemoizedPointScorer(lambda x: x[:, 0]+10)
    points = np.array([[1., 2.]])
    result = first(points)
    result[0] = 99
    assert first(points)[0] == 1 and second(points)[0] == 11
    assert first(np.empty((0, 2))).shape == (0,)


def test_failed_scores_are_not_cached_and_negative_infinity_is_supported():
    cached = MemoizedPointScorer(lambda x: np.full(len(x), np.nan))
    with pytest.raises(ValueError):
        cached(np.zeros((2, 2)))
    assert cached.evaluated_points == 0
    cached.score = lambda x: np.full(len(x), -np.inf)
    assert np.isneginf(cached(np.zeros((2, 2)))).all()
    assert cached.evaluated_points == 1


def test_nonfinite_or_wrong_dimension_points_rejected():
    cached = MemoizedPointScorer(lambda x: np.zeros(len(x)))
    for points in [np.ones(2), np.ones((2, 3)), np.array([[np.nan, 1.]])]:
        with pytest.raises(ValueError):
            cached(points)
