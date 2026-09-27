from __future__ import annotations

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPORT = HERE.parent.parent


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def load(name: str) -> dict:
    return json.loads((HERE / name).read_text())


def test_frozen_design_source_lock_and_result_inputs_match() -> None:
    design = load("design_variants.json")
    lock = load("source_lock.json")
    result = load("results.json")
    assert lock["stage"] == "frozen_before_candidate_outcomes"
    assert lock["design_sha256"] == digest(HERE / "design_variants.json")
    assert lock["adapter_sha256"] == digest(HERE / "run_transfer.py")
    assert design["dataset_cases_sha256"] == digest(HERE.parent / "cases.json")
    assert design["control_cases_sha256"] == digest(
        REPORT.parent / "2026_09_26_ds5_server_eval" / "dataset" / "cases.json"
    )
    assert result["dataset_cases_sha256"] == design["dataset_cases_sha256"]
    assert result["control_cases_sha256"] == design["control_cases_sha256"]
    assert result["design_sha256"] == lock["design_sha256"]
    assert result["source_lock_sha256"] == digest(HERE / "source_lock.json")
    assert result["candidate_seeded"] is False
    assert result["fresh_holdout_opened"] is False


def test_all_newdevelopment_reference_positives_are_retained_without_extras() -> None:
    summary = load("results.json")["summary"]
    expected = {"all": 129, "2500000": 62, "5000000": 67}
    groups = {"all": summary["all"], **summary["by_rate"]}
    for name, positives in expected.items():
        group = groups[name]
        assert group["reference_positives"] == positives
        assert group["candidate_positives"] == positives
        assert group["matched_reference_positives"] == positives
        assert group["lost_reference_positives"] == 0
        assert group["additional_candidate_positives"] == 0
        assert group["numerical_drift"]["selected_window_changes"] == 0
        assert group["numerical_drift"]["rank_order_changes"] == 0
        assert group["numerical_drift"]["projected_epoch_array_changes"] == 0


def test_identity_errors_stay_inside_preregistered_gates() -> None:
    result = load("results.json")
    assert len(result["rows"]) == 256
    assert len(result["control_rows"]) == 24
    for row in result["rows"] + result["control_rows"]:
        assert len(row["baseline_timings"]) == 3
        assert len(row["candidate_timings"]) == 3
        delta = row["drift"]["observation_delta"]
        if delta is not None:
            timing_us = abs(delta["circular_epoch_samples"]) / row["rate_hz"] * 1e6
            assert timing_us <= 2.0
            assert abs(delta["cfo_hz"]) <= 8000.0


def test_fixed_controls_preserve_exact_expected_labels() -> None:
    groups = load("results.json")["control_summary"]["groups"]
    for rate in (2_500_000, 5_000_000):
        pilot = groups[f"{rate}:pilot"]
        assert pilot == {
            "receiver_cases": 4,
            "baseline_positive": 4,
            "candidate_positive": 4,
            "matched_baseline": 4,
        }
        for kind in ("noise", "tone"):
            negative = groups[f"{rate}:{kind}"]
            assert negative["receiver_cases"] == 4
            assert negative["baseline_positive"] == 0
            assert negative["candidate_positive"] == 0


def test_costs_are_complete_and_reported_by_rate() -> None:
    summary = load("results.json")["summary"]
    assert summary["all"]["receiver_visits"] == 256
    assert summary["by_rate"]["2500000"]["receiver_visits"] == 128
    assert summary["by_rate"]["5000000"]["receiver_visits"] == 128
    for group in (summary["all"], *summary["by_rate"].values()):
        costs = group["costs"]
        assert costs["packed_unseeded_cpu_ms"] > 0
        assert costs["strided_candidate_cpu_ms"] > 0
        assert costs["cpu_speedup"] > 1
        assert costs["wall_speedup"] > 1
