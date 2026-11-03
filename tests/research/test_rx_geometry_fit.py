import copy

import numpy as np
import pytest

from tools.rx_geometry_fit import lane_loglik, objective, prepare, raw_features, signal_arrays


def document():
    lanes = []
    for split in ("calibration", "evaluation"):
        windows = []
        for i in range(4):
            windows.append(
                {
                    "role": "reception" if i < 2 else "held_frequency",
                    "prediction_utc_ns": i * 1000000000,
                    "source_window_id": f"{split}-{i}",
                    "sample_rate_hz": 5000000,
                    "observed": {rx: [{"canonical_rx0_hz": 1000.0}] for rx in ("rx0", "rx1")},
                    "predictions": [
                        {
                            "mu_canonical_rx0_hz": 1000.0,
                            "visible": True,
                            "los_enu_unit": {"east": 0.1 * i, "north": 0.2, "up": 0.8},
                        }
                    ],
                }
            )
        lanes.append(
            {
                "lane": {"session_id": split},
                "recording_split": split,
                "alias_period_hz": 227272.727,
                "windows": windows,
                "components": [
                    {"kind": "track_candidate", "log_prior": 0.0},
                    {"kind": "other", "log_prior": None},
                ],
            }
        )
    return {"schema": "rx-geometry-dataset/v1", "lanes": lanes}


def test_nested_likelihoods_and_control_scope():
    doc = document()
    lanes, _, _ = prepare(doc)
    signal_arrays(lanes, 2500.0)
    beta = np.array([0.2, 0.4, 0.1])
    d = lane_loglik(lanes[0], beta, np.array([1.0, 2.0]))
    s = lane_loglik(lanes[0], np.pad(beta, (0, 3)), np.array([1.0, 2.0]))
    t = lane_loglik(lanes[0], np.pad(beta, (0, 5)), np.array([1.0, 2.0]))
    np.testing.assert_array_equal(d, s)
    np.testing.assert_array_equal(s, t)
    source = doc["lanes"][0]
    x, v, mu = raw_features(source)
    swap, sv, smu = raw_features(source, "swap")
    np.testing.assert_array_equal(x[..., :6], swap[..., :6])
    np.testing.assert_array_equal(x[..., 6:], -swap[..., 6:])
    reverse, rv, rmu = raw_features(source, "reverse")
    np.testing.assert_array_equal(x[..., :3], reverse[..., :3])
    np.testing.assert_array_equal(reverse[:2, ..., 3:], x[1::-1, ..., 3:])
    for other in (sv, rv):
        np.testing.assert_array_equal(v, other)
    for other in (smu, rmu):
        np.testing.assert_array_equal(mu, other)


def test_calibration_objective_and_scaler_ignore_evaluation_and_held_values():
    original = document()
    changed = copy.deepcopy(original)
    for lane in changed["lanes"]:
        for window in lane["windows"]:
            if lane["recording_split"] == "evaluation" or window["role"] == "held_frequency":
                window["predictions"][0]["los_enu_unit"]["east"] = 99.0
                window["observed"]["rx0"] = []
    a, ac, ast = prepare(original)
    b, bc, bst = prepare(changed)
    np.testing.assert_array_equal(ac, bc)
    np.testing.assert_array_equal(ast, bst)
    signal_arrays(a, 2500.0, calibration_only=True)
    signal_arrays(b, 2500.0, calibration_only=True)
    assert objective(np.zeros(8), a, 8, np.ones(2)) == objective(np.zeros(8), b, 8, np.ones(2))
    assert not np.any(a[1]["signal"])


def test_missing_evaluation_population_rejected():
    doc = document()
    doc["lanes"].pop()
    with pytest.raises(ValueError, match="empty evaluation"):
        prepare(doc)
