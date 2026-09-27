from __future__ import annotations

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
RESULT_SHA256 = "80fbea5f98731f1f659b74468b9f03d5564eaa6a357f98230e5012e44ba08507"


def load(name: str) -> dict:
    return json.loads((HERE / name).read_text())


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def test_result_is_complete_and_bound_to_frozen_inputs() -> None:
    result = load("results.json")
    lock = load("source_lock.json")
    assert digest(HERE / "results.json") == "sha256:" + RESULT_SHA256
    assert result["status"] == "complete"
    assert result["performance_timing_valid"] is False
    assert result["candidate_seeded"] is False
    assert result["maximum_candidates"] == 1
    assert result["automatic_fallback"] is False
    assert result["frozen_sources"] == lock["files"]
    assert result["design_sha256"] == lock["files"]["design"]
    assert len(result["rows"]) == 40
    assert len({(row["case_id"], row["rx"]) for row in result["rows"]}) == 40


def test_fp32_preserves_reference_identity_gate() -> None:
    result = load("results.json")
    summary = result["summary"]["all"]
    assert result["identity_gate_pass"] is True
    assert summary["receiver_cases"] == 40
    assert summary["reference_positive"] == 32
    assert summary["candidate_positive"] == 32
    assert summary["matched_reference_positive"] == 32
    for key in (
        "lost_reference_positive",
        "additional_candidate_positive",
        "selected_window_changes",
        "rank_order_changes",
        "projected_epoch_array_changes",
    ):
        assert summary[key] == 0
    assert summary["maximum_first_proposal_timing_error_us"] < 2.0
    assert summary["maximum_first_proposal_cfo_error_hz"] < 8000.0


def test_rate_kind_labels_and_constructed_truth_are_reported_separately() -> None:
    groups = load("results.json")["summary"]["by_rate_kind"]
    for rate in (2_500_000, 5_000_000):
        expected = {
            "pilot": (12, 12),
            "noise": (2, 0),
            "tone": (2, 0),
            "two_pilot": (2, 2),
            "pilot_tone": (2, 2),
        }
        for kind, (receiver_cases, positives) in expected.items():
            group = groups[f"{rate}:{kind}"]
            assert group["receiver_cases"] == receiver_cases
            assert group["reference_positive"] == positives
            assert group["candidate_positive"] == positives
            assert group["matched_reference_positive"] == positives
            assert group["lost_reference_positive"] == 0
            assert group["additional_candidate_positive"] == 0
        for kind in ("noise", "tone"):
            truth = groups[f"{rate}:{kind}"]["constructed_truth"]
            assert truth["reference"]["pilot_truth_receiver_cases"] == 0
            assert truth["candidate"]["pilot_truth_receiver_cases"] == 0
        mixture = groups[f"{rate}:two_pilot"]["constructed_truth"]
        for side in ("reference", "candidate"):
            assert mixture[side]["any_supported_coordinate_match"] == 2
            assert mixture[side]["supported_trajectory_matches"] == {"a": 2, "b": 0}


def test_result_contains_no_performance_timings() -> None:
    serialized = json.dumps(load("results.json")).lower()
    for key in ("cpu_ms", "wall_ms", "speedup", "repetitions", "warmup"):
        assert key not in serialized
