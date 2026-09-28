import pytest

from tools.rx_sequence_case_audit import EPOCH_PERIOD_NS, build_audit


def test_audit_retains_ambiguity_bounds_runs_and_epoch_evidence():
    seq = {
        "sequences": [
            {
                "hypothesis_id": "h",
                "role": "reception",
                "uncensored_lag_rx1_minus_rx0_s": 1.0,
                "receivers": {"rx0": {"first_hit_utc_ns": 20}, "rx1": {"first_hit_utc_ns": 20}},
            }
        ]
    }
    rows = []
    statuses = {
        0: ["no_matching_candidate", "unique_hit", "unique_hit"],
        1: ["ambiguous_candidate", "no_matching_candidate", "unique_hit"],
    }
    for rid in (0, 1):
        for n, status in enumerate(statuses[rid]):
            rows.append(
                {
                    "hypothesis_id": "h",
                    "role": "reception",
                    "receiver_id": rid,
                    "source_window_id": f"w{n}",
                    "prediction_utc_ns": n * 10,
                    "window_start_utc_ns": n * 10 - 1,
                    "window_end_utc_ns": n * 10 + 1,
                    "status": status,
                    "matches": []
                    if status != "unique_hit"
                    else [{"candidate_id": f"c{rid}{n}", "detector_margin": 0.2}],
                }
            )
    opportunities = []
    for n in (1, 2):
        receivers = {}
        for rid in (0, 1):
            receivers[f"rx{rid}"] = {
                "receiver_id": rid,
                "candidates": [
                    {
                        "candidate_id": f"c{rid}{n}",
                        "fractional_exact_score": 0.3,
                        "fractional_control_score": 0.1,
                        "fractional_margin": 0.2,
                        "fractional_epoch_offset_samples": 0.25 + rid,
                        "integer_epoch_sample": 100 + rid,
                        "source_interval": {
                            "source_group_id": "g",
                            "source_sample_start": 100,
                            "source_sample_end": 200,
                            "support_center_utc_ns": 1000 + rid * (round(EPOCH_PERIOD_NS) + 100),
                        },
                    }
                ],
            }
        opportunities.append({"source_window_id": f"w{n}", "receivers": receivers})
    result = build_audit(seq, rows, opportunities)
    case = result["cases"][0]
    assert result["case_count"] == result["uncensored_lag_case_count"] == 1
    assert case["receivers"]["rx0"]["first_hit_interval"]["valid"] is True
    assert case["receivers"]["rx1"]["first_hit_interval"]["valid"] is False
    assert (
        case["receivers"]["rx1"]["first_hit_interval"]["reason"]
        == "earlier_eligible_observation_is_ambiguous_or_invalid"
    )
    assert case["receivers"]["rx0"]["unique_hit_runs"][0]["window_count"] == 2
    assert (
        case["receivers"]["rx0"]["eligible_observations"][1]["matches"][0]["fractional_exact_score"]
        == 0.3
    )
    common = case["common_dual_unique_hit_windows"]
    assert len(common) == 1
    assert common[0]["proxy_epoch_compatible"] is True
    assert abs(common[0]["support_center_epoch_phase_delta_rx1_minus_rx0_ns"]) < 101
    assert common[0]["integer_epoch_sample_delta_rx1_minus_rx0"] == 1
    assert (
        case["receivers"]["rx0"]["eligible_observations"][1]["matches"][0][
            "fractional_epoch_offset_samples"
        ]
        == 0.25
    )
    assert case["receivers"]["rx0"]["cadence_gaps_s"] == [1e-08, 1e-08]


def test_missing_raw_match_and_duplicate_rows_fail_closed():
    sequences = {
        "sequences": [
            {
                "hypothesis_id": "h",
                "role": "reception",
                "receivers": {"rx0": {"first_hit_utc_ns": 1}, "rx1": {"first_hit_utc_ns": 1}},
            }
        ]
    }
    row = {
        "hypothesis_id": "h",
        "role": "reception",
        "receiver_id": 0,
        "source_window_id": "w",
        "prediction_utc_ns": 1,
        "status": "unique_hit",
        "matches": [{"candidate_id": "missing"}],
    }
    with pytest.raises(ValueError, match="lacks raw opportunity"):
        build_audit(sequences, [row], [{"source_window_id": "w", "receivers": {}}])
    with pytest.raises(ValueError, match="duplicate matched opportunity"):
        build_audit(sequences, [row, row], [{"source_window_id": "w", "receivers": {}}])
