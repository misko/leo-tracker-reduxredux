import copy

import numpy as np
import pytest

import tools.rx_nominal_beam_cv as module
from tools.rx_causal_geometry_cv import training_reception_document


def _lane(session, channel, split="calibration"):
    return {
        "recording_split": split,
        "lane": {"session_id": session, "channel": channel},
        "windows": [
            {"role": "reception", "source_window_id": f"{session}-{channel}-r"},
            {"role": "held_frequency", "source_window_id": f"{session}-{channel}-h"},
        ],
    }


def _document():
    return {
        "schema": "rx-geometry-dataset/v1",
        "lanes": [_lane(f"s{i}", channel) for i in range(6) for channel in (0, 1)]
        + [_lane("evaluation", 0, "evaluation")],
    }


def test_training_isolation_physically_removes_held_and_evaluation():
    document = _document()
    changed = copy.deepcopy(document)
    for lane in changed["lanes"]:
        if lane["lane"]["session_id"] == "s0" or lane["recording_split"] == "evaluation":
            lane["windows"] = None
        else:
            lane["windows"][1]["observed"] = None
            lane["windows"][1]["predictions"] = None
    restricted = training_reception_document(changed, "s0")
    assert {lane["lane"]["session_id"] for lane in restricted["lanes"]} == {
        f"s{i}" for i in range(1, 6)
    }
    assert all(
        [window["role"] for window in lane["windows"]] == ["reception"]
        for lane in restricted["lanes"]
    )


def test_fold_membership_and_bounds():
    assert module.calibration_sessions(_document()) == [f"s{i}" for i in range(6)]
    with pytest.raises(ValueError, match="fold"):
        module.run_fold(_document(), 6)


def test_compact_diagnostics_counts_modes_and_hashes():
    receipt = [
        {
            "receivers": [
                {"windows": [{"nominees": [{"mode": "frozen_mu"}, {"mode": "orbit_increment"}]}]}
            ]
        }
    ]
    compact = module._compact_diagnostics(receipt)
    assert compact["receiver_windows"] == 1
    assert compact["nominee_rows"] == 2
    assert compact["mode_counts"] == {"frozen_mu": 1, "orbit_increment": 1}
    assert len(compact["sha256"]) == 64


def test_held_uniform_centers_using_held_record_reception(monkeypatch):
    sentinel = [{"roles": np.array(["reception", "held_frequency"])}]
    monkeypatch.setattr(module, "prepare_lanes", lambda *args: sentinel)
    monkeypatch.setattr(module, "attach_reference", lambda lanes, *args, **kwargs: lanes)
    calls = []

    def centered(lanes):
        calls.append(lanes)
        return lanes

    monkeypatch.setattr(module, "within_center_from_reception", centered)
    assert module._held_uniform({}, {}, np.zeros(8), np.ones(8)) is sentinel
    assert calls == [sentinel]


def test_nominal_beam_controls_preserve_non_target_arrays():
    from tools.rx_nominal_beam import beam_features

    x = np.zeros((2, 2, 2, 8))
    lane = {
        "x": x,
        "indices": [0, 1],
        "roles": np.array(["reception", "held_frequency"]),
        "visible": np.array([[True, False], [False, True]]),
        "prior": np.array([0.4, 0.6]),
        "signal": np.arange(8).reshape(2, 2, 2),
        "reference": np.array([1.0, 2.0]),
        "source": {
            "windows": [
                {
                    "predictions": [
                        {"los_enu_unit": {"east": 0.1, "up": 0.9}},
                        {"los_enu_unit": {"east": 0.2, "up": 0.8}},
                    ]
                },
                {
                    "predictions": [
                        {"los_enu_unit": {"east": 0.3, "up": 0.7}},
                        {"los_enu_unit": {"east": 0.4, "up": 0.6}},
                    ]
                },
            ]
        },
    }
    base = beam_features([lane], 1.0)[0]
    for control in ("swap", "geometryreverse", "geometrypermute"):
        changed = beam_features([lane], 1.0, control=control)[0]
        np.testing.assert_array_equal(changed["visible"], base["visible"])
        np.testing.assert_array_equal(changed["prior"], base["prior"])
        np.testing.assert_array_equal(changed["signal"], base["signal"])
        np.testing.assert_array_equal(changed["reference"], base["reference"])


def test_actual_five_record_preparation_chain_accepts_omitted_fold(monkeypatch):
    document = {
        "schema": "rx-geometry-dataset/v1",
        "lanes": [
            {
                "recording_split": "calibration",
                "lane": {"session_id": f"s{i}"},
                "alias_period_hz": 1_000.0,
                "windows": [
                    {
                        "role": "reception",
                        "source_window_id": f"w{i}",
                        "sample_rate_hz": 5_000_000,
                        "observed": {
                            "rx0": [{"canonical_rx0_hz": 10.0}],
                            "rx1": [],
                        },
                    }
                ],
            }
            for i in range(1, 6)
        ],
    }
    monkeypatch.setattr(module, "fit_background", lambda values, mode: {"rows": len(values)})
    monkeypatch.setattr(
        module,
        "full_reception_scaler",
        lambda document: (np.zeros(8), np.ones(8)),
    )
    sentinel = [{"x": np.zeros((1, 1, 2, 8))}]
    monkeypatch.setattr(module, "prepare_reception_lanes", lambda *args: sentinel)
    monkeypatch.setattr(module, "attach_reference", lambda lanes, *args, **kwargs: lanes)
    monkeypatch.setattr(module, "within_center", lambda lanes: lanes)
    prepared = module.prepare_five_record_training(document)
    assert [row["session_id"] for row in prepared["rows"]] == [f"s{i}" for i in range(1, 6)]
    assert prepared["uniform"] is sentinel
    assert prepared["background"] == {"rows": 5}
