import numpy as np
import pytest

from leo.analysis.polynomial_tracklets import TrackConfig, _piece
from leo.analysis.tracklet_fitting import finish_lane, prepare_lane


def test_common_finalization_preserves_original_indices_and_excludes_nonfinite():
    time = np.r_[np.linspace(30, 0, 61), np.nan]
    values = 30_000 - 500 * time
    t, y, order, n = prepare_lane(time, values)
    piece = _piece(t, y, np.arange(len(t)), 1)
    result = finish_lane(t, y, order, n, [piece], TrackConfig(), "test")
    assert len(result["tracks"]) == 1
    np.testing.assert_array_equal(result["assignment"][:-1], np.zeros(61, int))
    assert result["assignment"][-1] == -1
    assert result["diagnostics"]["nonfinite_points"] == 1


def test_duplicate_proposals_never_duplicate_support_or_inflate_tracks():
    t, y, order, n = prepare_lane(np.linspace(0, 30, 61), np.linspace(0, 15_000, 61))
    piece = _piece(t, y, np.arange(len(t)), 1)
    result = finish_lane(t, y, order, n, [piece, piece.copy()], TrackConfig(), "test")
    assert len(result["tracks"]) == 1
    assert len(result["tracks"][0]["indices"]) == n


def test_common_finalization_does_not_add_unproposed_points():
    t, y, order, n = prepare_lane(np.linspace(0, 30, 61), np.linspace(0, 15_000, 61))
    piece = _piece(t, y[::2], np.arange(0, len(t), 2), 1)
    result = finish_lane(t, y, order, n, [piece], TrackConfig(), "test")
    np.testing.assert_array_equal(result["assignment"][1::2], -np.ones(30, int))


def test_prepare_rejects_mismatched_shapes():
    with pytest.raises(ValueError):
        prepare_lane([0, 1], [2])
