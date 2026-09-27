from __future__ import annotations

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def load():
    return json.loads((HERE / "phase1_cost_results.json").read_text())


def test_phase_one_receipt_is_complete_stable_and_stops_before_phase_two():
    result = load()
    assert result["status"] == "complete"
    assert result["complete_gate_passed"]
    assert result["source_lock_stable"]
    assert len(result["rows"]) == 4
    assert result["cost_gate_passed"]
    assert not result["scientific_gate_passed"]
    assert not result["phase2_authorized"]
    assert not result["holdout_opened"]


def test_phase_one_has_exact_repetition_and_state_accounting():
    for row in load()["rows"]:
        assert row["input_immutable"]
        assert row["repeat_outputs_deterministic"]
        assert row["candidate_state_commits"] == 1
        assert len(row["measurements"]) == 6
        assert {item["method"] for item in row["measurements"]} == {"application", "tg11"}
        for method in ("application", "tg11"):
            values = [item for item in row["measurements"] if item["method"] == method]
            assert [item["repeat"] for item in values] == [0, 1, 2]
            assert len({item["output_sha256"] for item in values}) == 1


def test_phase_one_records_the_single_scientific_failure_and_both_cost_passes():
    result = load()
    failures = [row for row in result["rows"] if not row["scientific"]["passed"]]
    assert [row["case_id"] for row in failures] == [
        "newdev-r2500000-scan-fw-40ebc07665464c7d-v001078"
    ]
    failure = failures[0]["scientific"]
    assert not failure["reference_active"]
    assert failure["candidate_active"]
    assert not failure["all_active_pairs_associated"]
    for rate in ("2500000", "5000000"):
        assert result["per_rate_summary"][rate]["cost_gate_passed"]


def test_phase_one_lock_and_result_hashes_are_self_consistent():
    result = load()
    for name, expected in result["source_lock"]["files"].items():
        assert hashlib.sha256(Path(name).read_bytes()).hexdigest() == expected
    assert hashlib.sha256((HERE / "control_results.json").read_bytes()).hexdigest() == (
        result["stage0_control_result_sha256"]
    )

