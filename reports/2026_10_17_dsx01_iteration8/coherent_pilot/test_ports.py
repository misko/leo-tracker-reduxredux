import importlib.util
from pathlib import Path

import numpy as np
import pytest

SPEC = importlib.util.spec_from_file_location(
    "coherent_pilot_ports", Path(__file__).with_name("ports.py")
)
ports = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ports)


def test_metadata_does_not_consume_cfo_or_descriptive_satellite_labels():
    rows = [
        dict(
            observation_id="a",
            time_s=1.0,
            actual_rf_hz=11e9,
            receiver=1,
            channel=4,
            measured_cfo_hz=5.0,
            original_best_satellite=123,
        )
    ]
    a = ports.metadata_only(rows)
    rows[0]["measured_cfo_hz"] = 999999.0
    rows[0]["original_best_satellite"] = 999
    b = ports.metadata_only(rows)
    assert np.array_equal(a.measured_hz, b.measured_hz) and not a.measured_hz.any()
    assert np.array_equal(a.times_s, b.times_s) and np.array_equal(a.receiver, [0])


def test_full_roles_retain_boundary_and_reject_unknown_or_duplicate_authority():
    membership = [
        dict(global_group_id=k, role=v)
        for k, v in [("a", "train"), ("b", "held"), ("c", "boundary")]
    ]
    masks = ports.role_masks(["a", "b", "c"], membership)
    assert [int(m.sum()) for m in masks.values()] == [1, 1, 1]
    with pytest.raises(ValueError):
        ports.role_masks(["a"], membership + [membership[0]])
    with pytest.raises(ValueError):
        ports.role_masks(["a"], [dict(global_group_id="a", role="unknown")])


def test_partition_rejects_cross_lane_and_keeps_every_point():
    rows = [
        dict(observation_id=str(i), time_s=float(i), actual_rf_hz=11e9, receiver=1, channel=4)
        for i in range(3)
    ]
    obs = ports.metadata_only(rows)
    result = ports.partition(np.array([0, 0, 1]), obs)
    assert result["rows"] == 3 and result["groups"] == 2 and result["all_rows_once"]
    obs.rf_hz[1] += 1
    with pytest.raises(ValueError):
        ports.partition(np.array([0, 0, 1]), obs)
    with pytest.raises(ValueError):
        ports.partition(np.array([0, 2, 2]), obs)


def test_prediction_comparison_includes_every_field():
    ports.same_predictions(dict(x=np.array([1.0])), dict(x=np.array([1.0])))
    with pytest.raises(AssertionError):
        ports.same_predictions(dict(x=np.array([1.0])), dict(x=np.array([2.0])))
