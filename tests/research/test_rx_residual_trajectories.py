import copy
import json

import numpy as np
import pytest

from tools.rx_residual_trajectories import analyze


def _document():
    def window(window_id, role, time_ns, mu, frequencies):
        return {
            "source_window_id": window_id,
            "role": role,
            "prediction_utc_ns": time_ns,
            "observed": {
                "rx0": [
                    {"candidate_id": f"{window_id}-{index}", "canonical_rx0_hz": value}
                    for index, value in enumerate(frequencies)
                ],
                "rx1": [],
            },
            "predictions": [
                {
                    "track_id": "track",
                    "catalog_number": 1,
                    "mu_canonical_rx0_hz": mu,
                    "visible": True,
                },
                {
                    "track_id": "track",
                    "catalog_number": 2,
                    "mu_canonical_rx0_hz": mu + 2_000.0,
                    "visible": False,
                },
            ],
        }

    return {
        "schema": "rx-geometry-dataset/v1",
        "lanes": [
            {
                "recording_split": "calibration",
                "lane": {"session_id": "s", "channel": 1},
                "alias_period_hz": 10_000.0,
                "components": [
                    {
                        "kind": "track_candidate",
                        "track_id": "track",
                        "catalog_number": 1,
                        "rank": 1,
                        "log_prior": np.log(0.8),
                    },
                    {
                        "kind": "track_candidate",
                        "track_id": "track",
                        "catalog_number": 2,
                        "rank": 2,
                        "log_prior": np.log(0.2),
                    },
                    {"kind": "other", "log_prior": None},
                ],
                "windows": [
                    window("r0", "reception", 1_000_000_000, 9_900.0, [100.0, 4_000.0]),
                    window("r1", "reception", 2_000_000_000, 100.0, [250.0]),
                    window("h0", "held_frequency", 5_000_000_000, 300.0, [500.0]),
                ],
            }
        ],
    }


def test_wrapped_signed_nearest_residual_and_empty_receiver() -> None:
    result = analyze(_document())
    nominee = result["lanes"][0]["nominees"][0]
    rx0, rx1 = nominee["receivers"]
    nearest = rx0["windows"][0]["nearest"]
    assert nearest["signed_residual_hz"] == pytest.approx(200.0)
    assert nearest["candidate_index"] == 0
    assert rx1["windows"][0]["nearest"] is None
    assert rx1["role_stats"]["reception"]["observed_fraction"] == 0.0


def test_steps_and_exact_role_boundary_are_exported() -> None:
    rx0 = analyze(_document())["lanes"][0]["nominees"][0]["receivers"][0]
    assert len(rx0["adjacent_steps"]) == 2
    assert rx0["adjacent_steps"][0]["forecast_step_hz"] == pytest.approx(200.0)
    boundary = rx0["role_boundary"]
    assert boundary["gap_s"] == pytest.approx(3.0)
    assert boundary["last_reception_source_window_id"] == "r1"
    assert boundary["first_held_source_window_id"] == "h0"
    assert boundary["forecast_step_hz"] == pytest.approx(200.0)


def test_role_fractions_keep_empty_and_invisible_as_zero() -> None:
    result = analyze(_document())
    visible = result["lanes"][0]["nominees"][0]["receivers"][0]
    invisible = result["lanes"][0]["nominees"][1]["receivers"][0]
    assert visible["role_stats"]["reception"]["within_500hz_fraction"] == pytest.approx(1.0)
    assert invisible["role_stats"]["reception"]["within_1500hz_fraction"] == 0.0


def test_all_nominees_and_normalized_prior_are_preserved() -> None:
    lane = analyze(_document())["lanes"][0]
    assert len(lane["nominees"]) == 2
    np.testing.assert_allclose([row["prior_probability"] for row in lane["nominees"]], [0.8, 0.2])
    assert lane["nomination_summary"]["weight_ge_1e_6_count"] == 2


def test_input_is_immutable_and_evaluation_lanes_are_excluded() -> None:
    document = _document()
    evaluation = copy.deepcopy(document["lanes"][0])
    evaluation["recording_split"] = "evaluation"
    evaluation["lane"]["session_id"] = "evaluation"
    document["lanes"].append(evaluation)
    before = copy.deepcopy(document)
    result = analyze(document)
    assert document == before
    assert result["calibration_records"] == ["s"]


def test_nearest_tie_uses_first_saved_candidate_deterministically() -> None:
    document = _document()
    window = document["lanes"][0]["windows"][0]
    window["predictions"][0]["mu_canonical_rx0_hz"] = 0.0
    window["observed"]["rx0"] = [
        {"candidate_id": "first", "canonical_rx0_hz": -100.0},
        {"candidate_id": "second", "canonical_rx0_hz": 100.0},
    ]
    nearest = analyze(document)["lanes"][0]["nominees"][0]["receivers"][0]["windows"][0]["nearest"]
    assert nearest["candidate_index"] == 0
    assert nearest["candidate_id"] == "first"
    assert nearest["signed_residual_hz"] == pytest.approx(-100.0)


def test_null_prior_serializes_without_nonfinite_json() -> None:
    document = _document()
    document["lanes"][0]["components"][1]["log_prior"] = None
    result = analyze(document)
    nominee = result["lanes"][0]["nominees"][1]
    assert nominee["normalized_log_prior"] is None
    assert nominee["prior_probability"] == 0.0
    json.dumps(result, allow_nan=False)
