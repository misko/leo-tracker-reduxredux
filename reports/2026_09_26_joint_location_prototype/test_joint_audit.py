"""Independent adversarial checks for the joint-location numerical policy."""

from __future__ import annotations

import numpy as np

from joint_core import (
    CAP_HZ,
    TrackPrediction,
    choose_scan_clock,
    profile_track,
    rank_hypotheses,
    score_location,
    score_profiled_location,
)


def _profile(rms: float, reserved: float = 1.0) -> list[dict]:
    return [
        {
            "track_id": "t",
            "candidate_id": "1",
            "tau_s": 0.0,
            "cfo_hz": 0.0,
            "training_rms_hz": rms,
            "reserved_rms_hz": reserved,
        }
    ]


def _compact(scan_id: str, weight: int, rms: float, reserved: float = 1.0):
    return (scan_id, [(weight, np.array([0.0]), _profile(rms, reserved))])


def test_missing_hard_shared_tau_is_a_capped_failure_not_free_clock_evidence():
    profiles = [
        [None, {"training_rms_hz": 20.0}],
        [{"training_rms_hz": 0.0}, {"training_rms_hz": 100.0}],
    ]
    result = choose_scan_clock(profiles, [-1.0, 1.0], 0.0, hard_shared=True)
    assert result["clock_tau_s"] == 1.0
    assert result["training_objective"] == 20.0**2 + 100.0**2


def test_duration_weight_changes_the_shared_clock_when_tracks_disagree():
    profiles = [
        [{"training_rms_hz": 0.0}, {"training_rms_hz": 10.0}],
        [{"training_rms_hz": 10.0}, {"training_rms_hz": 0.0}],
    ]
    assert choose_scan_clock(profiles, [-1.0, 1.0], 0.0, hard_shared=True)[
        "clock_tau_s"
    ] == -1.0
    assert choose_scan_clock(
        profiles, [-1.0, 1.0], 0.0, hard_shared=True, weights=[1, 10]
    )["clock_tau_s"] == 1.0


def test_equal_scan_primary_can_reverse_duration_pooled_ranking():
    uneven = score_profiled_location(
        [_compact("long", 100, 10.0), _compact("short", 1, 100.0)], 0.0
    )
    steady = score_profiled_location(
        [_compact("long", 100, 20.0), _compact("short", 1, 20.0)], 0.0
    )
    assert uneven["regularized_pooled_rms_hz"] < steady["regularized_pooled_rms_hz"]
    assert uneven["regularized_equal_scan_rms_hz"] > steady["regularized_equal_scan_rms_hz"]


def test_penalized_ranking_is_per_model_and_preserves_complete_hypothesis():
    rows = [
        {"location_id": "a", "model": "lambda_0", "regularized_equal_scan_rms_hz": 2.0, "scans": ["a0"]},
        {"location_id": "b", "model": "lambda_0", "regularized_equal_scan_rms_hz": 1.0, "scans": ["b0"]},
        {"location_id": "a", "model": "lambda_100", "regularized_equal_scan_rms_hz": 1.0, "scans": ["a100"]},
        {"location_id": "b", "model": "lambda_100", "regularized_equal_scan_rms_hz": 3.0, "scans": ["b100"]},
    ]
    winners = {
        model: rank_hypotheses(
            [row for row in rows if row["model"] == model],
            1,
            "regularized_equal_scan_rms_hz",
        )[0]
        for model in ("lambda_0", "lambda_100")
    }
    assert winners["lambda_0"]["location_id"] == "b"
    assert winners["lambda_0"]["scans"] == ["b0"]
    assert winners["lambda_100"]["location_id"] == "a"
    assert winners["lambda_100"]["scans"] == ["a100"]


def test_compact_and_array_scoring_are_identical():
    track = TrackPrediction(
        track_id="t",
        weight_s=7,
        candidate_ids=("1",),
        taus_s=np.array([0.0]),
        measured_hz=np.array([0.0, 2.0, 0.0, 4.0]),
        predicted_hz=np.zeros((1, 1, 4)),
        training_mask=np.array([True, True, False, False]),
        visible=np.array([True]),
    )
    array_result = score_location([("s", [track])], 100.0)
    compact = [("s", [(track.weight_s, track.taus_s, profile_track(track))])]
    compact_result = score_profiled_location(compact, 100.0)
    for field in (
        "training_capped_weighted_rms_hz",
        "reserved_capped_weighted_rms_hz",
        "regularized_pooled_rms_hz",
        "regularized_equal_scan_rms_hz",
    ):
        assert compact_result[field] == array_result[field]


def test_reserved_scores_and_truth_fields_cannot_change_training_selection():
    base = [
        {"location_id": "a", "model": "m", "regularized_equal_scan_rms_hz": 1.0, "reserved_capped_weighted_rms_hz": 700.0, "reference_error_km": 900.0},
        {"location_id": "b", "model": "m", "regularized_equal_scan_rms_hz": 2.0, "reserved_capped_weighted_rms_hz": 1.0, "reference_error_km": 1.0},
    ]
    changed = [
        {**row, "reserved_capped_weighted_rms_hz": 800.0 - row["reserved_capped_weighted_rms_hz"], "reference_error_km": 1_000.0 - row["reference_error_km"]}
        for row in base
    ]
    assert rank_hypotheses(base, 1, "regularized_equal_scan_rms_hz")[0]["location_id"] == "a"
    assert rank_hypotheses(changed, 1, "regularized_equal_scan_rms_hz")[0]["location_id"] == "a"
