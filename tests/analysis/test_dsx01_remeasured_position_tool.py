"""Observation identity, alias and fallback invariants for CFO replacement."""

from types import SimpleNamespace

import numpy as np
import pytest
from prototype_dsx01_remeasured_position import apply_measurements


def fixture():
    period = 1 / 4.4e-6
    scan = SimpleNamespace(
        curved=[0],
        tracks=[
            dict(
                times=np.array([0.0, 1.0]),
                values=np.array([10 + period, 20 + period]),
                observation_ids=["a", "b"],
                receiver=1,
                channel=2,
            ),
            dict(
                times=np.array([0.0]),
                values=np.array([99.0]),
                observation_ids=["linear"],
                receiver=2,
                channel=7,
            ),
        ],
    )
    rows = {
        k: dict(
            receiver=1,
            channel=2,
            original_cfo_hz=raw,
            glrt64=dict(accepted=k == "a", residual_cfo_hz=3),
        )
        for k, raw in [("a", 10), ("b", 20)]
    }
    return scan, rows


def test_replacement_keeps_alias_ids_times_linear_tracks_and_failed_measurements():
    scan, rows = fixture()
    old = scan.tracks[0]["values"].copy()
    metadata = apply_measurements(scan, rows, "glrt64")
    np.testing.assert_allclose(scan.tracks[0]["values"], old + [3, 0])
    np.testing.assert_array_equal(scan.tracks[0]["times"], [0, 1])
    assert scan.tracks[0]["observation_ids"] == ["a", "b"]
    assert scan.tracks[1]["values"][0] == 99
    assert metadata["corrected"] == 1 and metadata["fallback"] == 1


def test_missing_points_wrong_receiver_or_original_value_fail_closed():
    scan, rows = fixture()
    with pytest.raises(ValueError, match="exactly"):
        apply_measurements(scan, {"a": rows["a"]}, "original")
    rows["a"]["receiver"] = 2
    with pytest.raises(ValueError, match="receiver"):
        apply_measurements(scan, rows, "original")
    rows["a"]["receiver"] = 1
    rows["a"]["original_cfo_hz"] += 1
    with pytest.raises(ValueError, match="alias"):
        apply_measurements(scan, rows, "original")
