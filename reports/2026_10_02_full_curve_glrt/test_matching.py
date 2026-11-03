import numpy as np
import pytest
from matching import ALIAS_HZ, assign_groups, circular_residual, connected_support, robust_line


def test_alias_invariance():
    values = np.array([-1000, 0, 1500])
    np.testing.assert_allclose(
        circular_residual(values + 4 * ALIAS_HZ, np.zeros(3)), values, atol=1e-8
    )


def test_duplicate_alternatives_are_one_observation():
    residual = np.array([[100, 50, 300], [1000, 1500, 2000]])
    result = assign_groups(residual, np.array([10, 10, 30]))
    assert result["rows"].tolist() == [1, 2]
    assert result["accepted"].tolist() == [True, True]


def test_crossing_abstains():
    result = assign_groups(np.array([[100, 200], [110, 2000]]), np.array([0, 1]))
    assert result["accepted"].tolist() == [False, True]


def test_invisible_candidates_abstain():
    result = assign_groups(np.full((2, 3), np.inf), np.arange(3))
    assert not np.any(result["accepted"])


def test_gap_splits_support_without_inventing_points():
    times = np.r_[np.arange(0, 16, 2), np.arange(30, 46, 2)]
    assignment = assign_groups(np.zeros((1, 16)), np.arange(16))
    coherent, segments = connected_support(assignment, times, np.ones(16), np.zeros(16))
    assert len(segments) == 2
    assert np.all(coherent)
    assert segments[0]["end_s"] == 14
    assert segments[1]["start_s"] == 30


def test_sparse_hits_are_not_tracks():
    times = np.arange(0, 100, 10)
    assignment = assign_groups(np.zeros((1, 10)), np.arange(10))
    coherent, segments = connected_support(assignment, times, np.ones(10), np.zeros(10))
    assert not np.any(coherent)
    assert not segments


def test_bounded_shared_fit():
    times = np.linspace(-150, 150, 100)
    intercept, slope = robust_line(times, -8000 + 7 * times, np.ones(100), (-7000, 0))
    assert intercept == pytest.approx(-8000, abs=0.01)
    assert slope == pytest.approx(7, abs=0.01)
    _, slope = robust_line(times, -8000 + 30 * times, np.ones(100), (-8000, 0))
    assert slope == 10
