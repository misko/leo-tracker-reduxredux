import numpy as np
import pytest

from plot_final_glrt_orbit_tracks import final_tracks


class Arrays:
    def __init__(self, values):
        self.values = values

    def __getitem__(self, key):
        return self.values[key]


def test_final_tracks_validates_sorts_and_computes_rms():
    arrays = Arrays(
        {
            "catalog_numbers": np.array([10]),
            "times_s": np.array([2.0, 1.0]),
            "group": np.array([100, 101]),
            "receiver": np.array([1, 1]),
            "residual_hz": np.array([[3.0], [4.0]]),
        }
    )
    rows = [
        {
            "scan_label": "A",
            "catalog_number": "10",
            "receiver": "1",
            "group": "100",
            "owner_state": "seed-owned",
            "viterbi_row": "0",
            "viterbi_changed": "False",
        },
        {
            "scan_label": "A",
            "catalog_number": "10",
            "receiver": "1",
            "group": "101",
            "owner_state": "unallocated",
            "viterbi_row": "1",
            "viterbi_changed": "True",
        },
    ]
    tracks = final_tracks(rows, arrays, "A")
    assert len(tracks) == 1
    np.testing.assert_array_equal(tracks[0]["rows"], [1, 0])
    np.testing.assert_array_equal(tracks[0]["seed_owned"], [False, True])
    np.testing.assert_array_equal(tracks[0]["changed"], [True, False])
    assert tracks[0]["duration_s"] == 1.0
    assert tracks[0]["rms_residual_hz"] == pytest.approx(np.sqrt(12.5))


def test_final_tracks_rejects_row_group_mismatch():
    arrays = Arrays(
        {
            "catalog_numbers": np.array([10]),
            "times_s": np.array([1.0]),
            "group": np.array([100]),
            "receiver": np.array([0]),
            "residual_hz": np.array([[0.0]]),
        }
    )
    rows = [
        {
            "scan_label": "A",
            "catalog_number": "10",
            "receiver": "0",
            "group": "999",
            "owner_state": "seed-owned",
            "viterbi_row": "0",
            "viterbi_changed": "False",
        }
    ]
    with pytest.raises(ValueError, match="group/receiver"):
        final_tracks(rows, arrays, "A")
