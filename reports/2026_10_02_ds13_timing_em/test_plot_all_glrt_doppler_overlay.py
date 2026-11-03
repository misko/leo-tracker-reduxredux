from types import SimpleNamespace

import numpy as np
import pytest
from plot_all_glrt_doppler_overlay import lane_masks, validate_plot_arrays


def synthetic_arrays():
    rows = 5
    satellites = 2
    dense = 7
    return SimpleNamespace(
        files=[
            "times_s",
            "receiver",
            "channel",
            "catalog_numbers",
            "dense_times_s",
            "dense_doppler_hz",
            "unshifted_tle_doppler_hz",
            "posterior",
            "accepted",
            "doppler_hz",
            "residual_hz",
        ],
        values={
            "times_s": np.arange(rows, dtype=float),
            "receiver": np.array([0, 0, 1, 1, 0]),
            "channel": np.array([1, 2, 1, 2, 1]),
            "catalog_numbers": np.array([10, 20]),
            "dense_times_s": np.arange(dense, dtype=float),
            "dense_doppler_hz": np.zeros((dense, satellites)),
            "unshifted_tle_doppler_hz": np.zeros((dense, satellites)),
            "posterior": np.zeros((rows, satellites)),
            "accepted": np.zeros((rows, satellites), dtype=bool),
            "doppler_hz": np.zeros((rows, satellites)),
            "residual_hz": np.zeros((rows, satellites)),
        },
    )


class Arrays:
    def __init__(self, source):
        self.files = source.files
        self.values = source.values

    def __getitem__(self, name):
        return self.values[name]


def test_all_glrt_rows_are_partitioned_once_without_posterior_selection():
    receiver = np.array([0, 0, 1, 1, 0])
    channel = np.array([1, 2, 1, 2, 1])
    lanes = lane_masks(receiver, channel)
    assert sum(int(mask.sum()) for _, _, mask in lanes) == len(receiver)
    assert {(rx, lane) for rx, lane, _ in lanes} == {(0, 1), (0, 2), (1, 1), (1, 2)}


def test_archived_array_validation_accepts_aligned_complete_data():
    source = synthetic_arrays()
    assert validate_plot_arrays(Arrays(source)) == (5, 2)


def test_archived_array_validation_rejects_non_boolean_association_mask():
    source = synthetic_arrays()
    source.values["accepted"] = source.values["accepted"].astype(int)
    with pytest.raises(ValueError, match="boolean"):
        validate_plot_arrays(Arrays(source))


def test_archived_array_validation_rejects_misaligned_satellite_matrix():
    source = synthetic_arrays()
    source.values["residual_hz"] = np.zeros((5, 1))
    with pytest.raises(ValueError, match="row/satellite"):
        validate_plot_arrays(Arrays(source))
