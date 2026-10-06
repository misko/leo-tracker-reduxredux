"""Stable Hough peak ordering must survive ties at the selection boundary."""

import numpy as np
import pytest

from leo.analysis.cfo_lines import _stable_top_indexes


@pytest.mark.parametrize("size", [1, 8, 100, 10000])
@pytest.mark.parametrize("distribution", ["zero", "ties", "continuous"])
def test_peak_selection_matches_stable_full_sort(size, distribution):
    rng = np.random.default_rng(621)
    values = {
        "zero": np.zeros(size),
        "ties": rng.integers(0, 8, size),
        "continuous": rng.normal(size=size),
    }[distribution]
    for count in (-1, 0, 1, min(7, size), size, size + 1):
        np.testing.assert_array_equal(
            _stable_top_indexes(values, count),
            np.argsort(values, kind="stable")[-count:],
        )


def test_boundary_tie_keeps_later_indexes():
    values = np.array([3.0, 2.0, 3.0, 2.0, 4.0, 2.0])
    np.testing.assert_array_equal(_stable_top_indexes(values, 4), [5, 0, 2, 4])


def test_complete_hough_result_matches_full_sort(monkeypatch):
    from leo.analysis import cfo_lines

    points = tuple(
        cfo_lines.CfoPoint(str(i), i * 0.1, 5000 + 2000 * i * 0.1, 0.9, 0.1, 0.8) for i in range(61)
    )
    actual = cfo_lines.weighted_hough_lines(points)
    assert actual
    monkeypatch.setattr(
        cfo_lines,
        "_stable_top_indexes",
        lambda values, count: np.argsort(values, kind="stable")[-count:],
    )
    assert cfo_lines.weighted_hough_lines(points) == actual
