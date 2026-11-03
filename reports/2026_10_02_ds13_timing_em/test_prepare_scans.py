from types import SimpleNamespace

import numpy as np
import pytest
from prepare_scans import ShiftedData, longest_tracks, select_scans


def test_selection_uses_chronological_extremes_not_result_or_signal_quality():
    captures = [{"session_id": name, "capture_start_utc_ns": start, "error_km": error}
                for name, start, error in [("middle", 2, 0), ("last", 3, 200), ("first", 1, 100)]]
    selected = select_scans({"dataset_id": "DS13", "captures": captures})
    assert [row["session_id"] for row in selected] == ["first", "last"]


def test_selection_rejects_duplicate_or_other_dataset():
    with pytest.raises(ValueError):
        select_scans({"dataset_id": "DS11"})
    with pytest.raises(ValueError):
        select_scans({"dataset_id": "DS13", "captures": [{"session_id": "same"}] * 2})


def test_longest_track_selection_balances_receivers():
    data = SimpleNamespace(times=np.arange(100.), tracks=[
        {"receiver": receiver, "track_id": f"{receiver}-{size}",
         "rows": np.arange(size)} for receiver in (0, 1) for size in (14, 15, 80)
    ])
    selected = longest_tracks(data, per_receiver=1)
    assert [track["track_id"] for track in selected] == ["0-80", "1-80"]


def test_common_shift_changes_only_orbit_timing_and_preserves_caller():
    original = np.arange(9., dtype=float)
    source = SimpleNamespace(predict=lambda parameters, **kwargs: parameters, times=[1])
    shifted = ShiftedData(source, 7)
    result = shifted.predict(original)
    np.testing.assert_array_equal(result[:6], original[:6])
    np.testing.assert_array_equal(result[6:], original[6:] + 7)
    np.testing.assert_array_equal(original, np.arange(9.))
    assert shifted.times == [1]
