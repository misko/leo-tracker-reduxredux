from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def result() -> dict:
    return json.loads((HERE / "results.json").read_text())


def test_complete_exact_result_and_preregistered_gate_failure() -> None:
    value = result()
    assert value["status"] == "complete"
    assert value["fresh_holdout_opened"] is False
    assert value["source_lock_stable"] is True
    assert value["elapsed_wall_ms"] < 120_000
    assert value["qualification"] == {
        "positive_path_cpu_gate": 3.0,
        "both_recorded_rates_pass": False,
        "negative_control_speed_gate": None,
    }
    assert len(value["rows"]) == 4
    assert all(row["all_responses_exact"] for row in value["rows"])


def test_positive_path_counts_explain_rate_specific_result() -> None:
    rows = {
        row["rate_hz"]: row
        for row in result()["rows"]
        if row["origin"] == "recorded_development_outcome_informed_positive_path"
    }
    assert rows[2_500_000]["candidate_diagnostic_counts"] == {
        "receiver_probe_acquisitions": 6,
        "candidate_scores": 60,
    }
    assert rows[5_000_000]["candidate_diagnostic_counts"] == {
        "receiver_probe_acquisitions": 12,
        "candidate_scores": 120,
    }
    assert rows[2_500_000]["summary"]["positive_path_cpu_gate_pass"] is True
    assert rows[5_000_000]["summary"]["positive_path_cpu_gate_pass"] is False


def test_zero_controls_complete_negative_schedule() -> None:
    controls = [
        row for row in result()["rows"]
        if row["origin"] == "constructed_all_zero_no_result_control"
    ]
    assert {row["rate_hz"] for row in controls} == {2_500_000, 5_000_000}
    for row in controls:
        assert row["response"]["first"] is None
        assert row["candidate_diagnostic_counts"] == {
            "receiver_probe_acquisitions": 22,
            "candidate_scores": 0,
        }
