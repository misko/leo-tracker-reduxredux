import copy
import math

import pytest

from tools.rx_partial_arc_support import analyze


def _lane(session="s", opposite=False):
    components = [
        {
            "kind": "track_candidate",
            "track_id": "t0",
            "catalog_number": 10,
            "rank": 1,
            "log_prior": math.log(0.2),
        },
        {
            "kind": "track_candidate",
            "track_id": "t1",
            "catalog_number": 10,
            "rank": 2,
            "log_prior": math.log(0.6),
        },
        {"kind": "other", "log_prior": math.log(0.2)},
    ]
    first = [-1.0, 0.0, 1.0]
    second = [value * (-1 if opposite else 1) + (0 if opposite else 5) for value in first]
    windows = []
    for index, (left, right) in enumerate(zip(first, second, strict=True)):
        windows.append(
            {
                "source_window_id": f"{session}-r{index}",
                "role": "reception",
                "prediction_utc_ns": index * 1_000_000_000,
                "predictions": [
                    {
                        "track_id": "t0",
                        "catalog_number": 10,
                        "los_enu_unit": {"east": left},
                        "visible": True,
                    },
                    {
                        "track_id": "t1",
                        "catalog_number": 10,
                        "los_enu_unit": {"east": right},
                        "visible": index != 0,
                    },
                ],
                "observed": {"rx0": [{"secret": index}], "rx1": []},
            }
        )
    windows.append(
        {
            **copy.deepcopy(windows[-1]),
            "source_window_id": f"{session}-h0",
            "role": "held_frequency",
            "prediction_utc_ns": 4_000_000_000,
        }
    )
    return {
        "recording_split": "calibration",
        "lane": {"session_id": session, "channel": 1, "edge": "lower"},
        "components": components,
        "windows": windows,
    }


def _document(lane):
    return {
        "schema": "rx-geometry-dataset/v1",
        "lanes": [lane, {**copy.deepcopy(lane), "recording_split": "evaluation"}],
    }


def test_constant_nominee_offsets_are_removed_and_priors_are_conditional():
    result = analyze(_document(_lane()), expected_records=1)
    lane = result["lanes"][0]
    role = lane["roles"]["reception"]
    assert role["prior_weighted_centered_trajectory_rms_disagreement"] == pytest.approx(0.0)
    assert role["mean_within_trajectory_excursion"] > 0
    assert role["prior_weighted_mean_within_trajectory_excursion"] > 0
    assert [row["conditional_retained_probability"] for row in role["nominees"]] == pytest.approx(
        [0.25, 0.75]
    )
    assert lane["retained_prior_mass_before_conditional_normalization"] == pytest.approx(0.8)
    assert lane["omitted_prior_mass"] == pytest.approx(0.2)
    assert role["visibility_gated"] is False
    assert role["nominees"][1]["visible_windows"] == 2
    assert result["calibration_sessions"] == ["s"]


def test_opposite_partial_arc_directions_have_positive_disagreement():
    role = analyze(_document(_lane(opposite=True)), expected_records=1)["lanes"][0]["roles"][
        "reception"
    ]
    assert role["prior_weighted_centered_trajectory_rms_disagreement"] > 0
    assert role["nominees"][0]["q_secant_per_s"] > 0
    assert role["nominees"][1]["q_secant_per_s"] < 0


def test_observed_outcome_perturbation_cannot_change_support():
    document = _document(_lane(opposite=True))
    changed = copy.deepcopy(document)
    for window in changed["lanes"][0]["windows"]:
        window["observed"] = {"rx0": [object(), object()], "rx1": [object()]}
    assert analyze(document, expected_records=1) == analyze(changed, expected_records=1)


def test_track_catalog_pairs_are_not_merged_and_times_must_align():
    lane = _lane()
    result = analyze(_document(lane), expected_records=1)
    assert len(result["lanes"][0]["roles"]["reception"]["nominees"]) == 2
    lane["windows"][1]["prediction_utc_ns"] = lane["windows"][0]["prediction_utc_ns"]
    with pytest.raises(ValueError, match="strictly increasing"):
        analyze(_document(lane), expected_records=1)
