from __future__ import annotations

import numpy as np
import pytest

from joint_core import CAP_HZ, TrackPrediction, choose_scan_clock, rank_hypotheses, score_location, score_profiled_location


def _track(track_id="t", visible=True, reserved_shift=0.0):
    # Candidate 0 prefers tau -1 (train RMS 0); candidate 1 prefers tau +1 (RMS 2).
    measured = np.array([0.0, 2.0, 0.0, 2.0 + reserved_shift])
    predicted = np.array(
        [
            [[0.0, 2.0, 0.0, 2.0], [0.0, 0.0, 0.0, 0.0]],
            [[0.0, 4.0, 0.0, 4.0], [0.0, 2.0, 0.0, 2.0]],
        ]
    )
    return TrackPrediction(track_id, 10, ("10", "20"), np.array([-1.0, 1.0]), measured, predicted, np.array([1, 1, 0, 0], bool), np.array([visible, visible]))


def test_clock_penalty_and_hard_shared_boundaries():
    profiles = [
        [{"training_rms_hz": 0.0}, {"training_rms_hz": 10.0}],
        [{"training_rms_hz": 10.0}, {"training_rms_hz": 0.0}],
    ]
    free = choose_scan_clock(profiles, [-1.0, 1.0], 0.0)
    hard = choose_scan_clock(profiles, [-1.0, 1.0], 0.0, hard_shared=True)
    assert free["choice_indices"] == [0, 1]
    assert hard["choice_indices"] == [0, 0]  # deterministic lower-clock tie
    assert choose_scan_clock(profiles, [-1.0, 1.0], 1_000.0)["choice_indices"] == [0, 0]
    with pytest.raises(ValueError, match="nonnegative"):
        choose_scan_clock(profiles, [-1.0, 1.0], -1)


def test_missing_tau_is_charged_and_duration_weights_clock():
    profiles = [
        [None, {"training_rms_hz": 10.0}],
        [{"training_rms_hz": 0.0}, {"training_rms_hz": 100.0}],
    ]
    # Missing first track cannot make -1 win; its capped loss is explicit.
    assert choose_scan_clock(profiles, [-1.0, 1.0], 0, hard_shared=True)["clock_tau_s"] == 1.0
    opposing = [
        [{"training_rms_hz": 0.0}, {"training_rms_hz": 10.0}],
        [{"training_rms_hz": 10.0}, {"training_rms_hz": 0.0}],
    ]
    assert choose_scan_clock(opposing, [-1.0, 1.0], 0, hard_shared=True, weights=[1, 10])["clock_tau_s"] == 1.0


def test_fixed_denominator_counts_invisible_track_as_capped_failure():
    result = score_location([("s", [_track("ok"), _track("missing", visible=False)])], 0.0)
    assert result["fixed_weight_seconds"] == 20
    assert result["training_capped_weighted_rms_hz"] == pytest.approx(CAP_HZ / np.sqrt(2))
    assert result["scans"][0]["tracks"][1] is None


def test_reserved_rows_never_select_identity_or_location():
    a = score_location([("s", [_track(reserved_shift=0.0)])], 0.0)
    b = score_location([("s", [_track(reserved_shift=100.0)])], 0.0)
    assert a["training_capped_weighted_rms_hz"] == b["training_capped_weighted_rms_hz"]
    assert a["scans"][0]["tracks"][0]["candidate_id"] == b["scans"][0]["tracks"][0]["candidate_id"]
    assert a["reserved_capped_weighted_rms_hz"] != b["reserved_capped_weighted_rms_hz"]


def test_complete_hypothesis_top_k_and_ties_are_deterministic():
    rows = [
        {"location_id": "b", "model": "m", "training_capped_weighted_rms_hz": 2, "scans": [1]},
        {"location_id": "a", "model": "m", "training_capped_weighted_rms_hz": 2, "scans": [2]},
        {"location_id": "c", "model": "m", "training_capped_weighted_rms_hz": 3, "scans": [3]},
    ]
    answer = rank_hypotheses(rows, 2)
    assert [row["location_id"] for row in answer] == ["a", "b"]
    assert [row["scans"] for row in answer] == [[2], [1]]


def test_each_scan_gets_an_independent_clock():
    taus=np.array([-1.0,1.0])
    left=[[{"training_rms_hz":0.0,"reserved_rms_hz":1.0},{"training_rms_hz":100.0,"reserved_rms_hz":1.0}]]
    right=[[{"training_rms_hz":100.0,"reserved_rms_hz":1.0},{"training_rms_hz":0.0,"reserved_rms_hz":1.0}]]
    result = score_profiled_location([("a", [(10,taus,left[0])]), ("b", [(10,taus,right[0])])], 1_000.0)
    assert [scan["clock_tau_s"] for scan in result["scans"]] == [-1.0, 1.0]


def test_joint_ranking_is_not_coordinate_averaging():
    rows = [
        {"location_id": "actual-candidate", "model": "m", "training_capped_weighted_rms_hz": 1.0, "latitude_deg": 10.0, "scans": [1, 2]},
        {"location_id": "other", "model": "m", "training_capped_weighted_rms_hz": 2.0, "latitude_deg": 20.0, "scans": [3, 4]},
    ]
    selected = rank_hypotheses(rows, 1)[0]
    assert selected["latitude_deg"] == 10.0
    assert selected["scans"] == [1, 2]
