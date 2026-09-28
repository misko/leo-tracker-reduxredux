import copy

import numpy as np

from tools.rx_causal_full_calibration import full_reception_scaler, prepare_families, run


def _lane(session, channel, split="calibration"):
    def window(role, index, east, observed):
        return {
            "role": role,
            "prediction_utc_ns": index * 1_000_000_000,
            "sample_rate_hz": 5_000_000,
            "source_window_id": f"{session}-{channel}-{role}-{index}",
            "observed": {
                "rx0": [{"canonical_rx0_hz": value} for value in observed],
                "rx1": [],
            },
            "predictions": [
                {
                    "track_id": "track",
                    "catalog_number": 1,
                    "los_enu_unit": {
                        "east": east,
                        "north": 0.0,
                        "up": np.sqrt(1 - east**2),
                    },
                    "mu_canonical_rx0_hz": 100.0,
                    "visible": True,
                }
            ],
        }

    return {
        "recording_split": split,
        "lane": {"session_id": session, "channel": channel},
        "alias_period_hz": 227_000.0,
        "components": [
            {
                "kind": "track_candidate",
                "track_id": "track",
                "catalog_number": 1,
                "log_prior": 0.0,
            },
            {"kind": "other", "log_prior": None},
        ],
        "windows": [
            window("reception", 1, 0.1, [90.0]),
            window("held_frequency", 2, 0.8, [50_000.0]),
        ],
    }


def _document():
    lanes = [_lane(f"s{index}", channel) for index in range(6) for channel in (1, 2)]
    lanes.append(_lane("evaluation", 1, "evaluation"))
    return {"schema": "rx-geometry-dataset/v1", "lanes": lanes}


def test_scaler_ignores_held_and_evaluation_geometry() -> None:
    document = _document()
    expected = full_reception_scaler(document)
    changed = copy.deepcopy(document)
    for lane in changed["lanes"]:
        if lane["recording_split"] == "evaluation":
            lane["windows"][0]["predictions"] = None
        else:
            lane["windows"][1]["predictions"] = None
    actual = full_reception_scaler(changed)
    np.testing.assert_array_equal(actual[0], expected[0])
    np.testing.assert_array_equal(actual[1], expected[1])


def test_family_preparation_ignores_held_and_evaluation_outcomes() -> None:
    document = _document()
    first = prepare_families(document)
    changed = copy.deepcopy(document)
    for lane in changed["lanes"]:
        windows = (
            lane["windows"] if lane["recording_split"] == "evaluation" else lane["windows"][1:]
        )
        for window in windows:
            window["observed"] = None
    second = prepare_families(changed)
    assert second["background"] == first["background"]
    np.testing.assert_array_equal(second["center"], first["center"])
    np.testing.assert_array_equal(second["scale"], first["scale"])
    for family in ("uniform", "causal"):
        for left, right in zip(first[family], second[family], strict=True):
            np.testing.assert_array_equal(left["x"], right["x"])
            np.testing.assert_array_equal(left["counts"], right["counts"])
            np.testing.assert_array_equal(left["reference"], right["reference"])
            np.testing.assert_array_equal(left["signal"], right["signal"])


def test_run_fits_both_families_from_same_membership(monkeypatch) -> None:
    import tools.rx_causal_full_calibration as module

    calls = []

    def fake_fit(lanes, old_fits):
        calls.append({lane["source"]["lane"]["session_id"] for lane in lanes})
        return {"schema": "rx-joint-geometry-fit/v1", "fits": {}}

    monkeypatch.setattr(module, "fit_arms", fake_fit)
    result = run(_document())
    assert calls == [set(result["calibration_sessions"]), set(result["calibration_sessions"])]
    assert result["training_source_window_count"] == 12
    assert set(result["families"]) == {"uniform", "causal"}
