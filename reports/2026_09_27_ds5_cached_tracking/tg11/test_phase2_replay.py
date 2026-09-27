"""Clerical and scientific-contract tests for the unexecuted phase-two runner."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import sys

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("tg11_phase2_runner", HERE / "run_phase2_replay.py")
RUNNER = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = RUNNER
spec.loader.exec_module(RUNNER)


def _phase1(case_ids: tuple[str, ...], lock: dict) -> dict:
    rows = []
    for case_id in case_ids:
        measurements = [
            {
                "method": method,
                "repeat": repeat,
                "process_cpu_ms": 1.0,
                "wall_ms": 1.0,
                "output_sha256": f"sha256:{method}",
            }
            for method in RUNNER.METHODS
            for repeat in range(RUNNER.EXPECTED_REPEATS)
        ]
        rows.append(
            {
                "case_id": case_id,
                "scientific": {"passed": True},
                "input_immutable": True,
                "repeat_outputs_deterministic": True,
                "candidate_state_commits": 1,
                "measurements": measurements,
            }
        )
    return {
        "status": "complete",
        "source_lock_stable": True,
        "complete_gate_passed": True,
        "scientific_gate_passed": True,
        "cost_gate_passed": True,
        "phase2_authorized": True,
        "holdout_opened": False,
        "selected_case_ids": list(case_ids),
        "stage0_control_result_sha256": "sha256:" + RUNNER.digest(RUNNER.STAGE0_RESULT),
        "source_lock": lock,
        "rows": rows,
        "per_rate_summary": {
            str(rate): {"cost_gate_passed": True} for rate in RUNNER.dataset.RATES
        },
    }


def test_phase1_validator_requires_exact_rows_repeats_and_determinism(
    monkeypatch, tmp_path: Path
) -> None:
    frozen = tmp_path / "frozen.txt"
    frozen.write_text("fixed")
    lock = {"files": {str(frozen): RUNNER.digest(frozen)}}
    lock_path = tmp_path / "source_lock_phase1.json"
    lock_path.write_text(json.dumps(lock))
    monkeypatch.setattr(RUNNER, "PHASE1_LOCK", lock_path)
    case_ids = ("a", "b", "c", "d")
    receipt = _phase1(case_ids, lock)
    RUNNER.validate_phase1(receipt, case_ids)

    receipt["rows"][0]["measurements"].pop()
    try:
        RUNNER.validate_phase1(receipt, case_ids)
    except ValueError:
        pass
    else:
        raise AssertionError("missing timing repeat must fail closed")

    receipt = _phase1(case_ids, lock)
    receipt["rows"][0]["measurements"][0]["output_sha256"] = "sha256:different"
    try:
        RUNNER.validate_phase1(receipt, case_ids)
    except ValueError:
        pass
    else:
        raise AssertionError("nondeterministic output must fail closed")


def test_actual_failed_phase1_receipt_cannot_authorize_phase2() -> None:
    receipt = RUNNER._load_json(RUNNER.PHASE1_RESULT)
    assert receipt["complete_gate_passed"] is True
    assert receipt["cost_gate_passed"] is True
    assert receipt["scientific_gate_passed"] is False
    assert receipt["phase2_authorized"] is False
    case_ids = tuple(case.id for case in RUNNER.dataset.timing_cases())
    try:
        RUNNER.validate_phase1(receipt, case_ids)
    except ValueError as error:
        assert "incomplete or failed" in str(error)
    else:
        raise AssertionError("failed phase-one science gate authorized phase two")


def _result(active: bool, pair=None):
    return SimpleNamespace(active=active, pair=pair)


def test_receiver_classification_preserves_losses_extras_and_associations(monkeypatch) -> None:
    case = SimpleNamespace()
    reference = SimpleNamespace(receiver=0)
    matched = RUNNER.dataset.Association(True, 0, None, (0.0, 0.0), (0.0, 0.0), "match")
    missed = RUNNER.dataset.Association(False, 0, None, None, None, "miss")

    monkeypatch.setattr(RUNNER.dataset, "associate_candidate_to_reference", lambda *_: matched)
    retained = RUNNER.classify_receiver(_result(True, object()), (reference,), case, 0)
    assert retained["outcome"] == "active_associated" and retained["passed"]

    monkeypatch.setattr(RUNNER.dataset, "associate_candidate_to_reference", lambda *_: missed)
    loss = RUNNER.classify_receiver(_result(False), (reference,), case, 0)
    extra = RUNNER.classify_receiver(_result(True, object()), (), case, 0)
    negative = RUNNER.classify_receiver(_result(False), (), case, 0)
    assert (loss["outcome"], loss["passed"]) == (
        "reference_positive_candidate_inactive",
        True,
    )
    assert (extra["outcome"], extra["passed"]) == ("extra", False)
    assert (negative["outcome"], negative["passed"]) == ("both_inactive", True)


def test_application_configuration_is_full_two_receiver_ten_candidate_geometry() -> None:
    case = RUNNER.dataset.real_cases()[0]
    config = RUNNER.configuration(case)
    assert config.maximum_acquisition_candidates == 10
    assert config.receiver_ids == (0, 1)
    assert config.scheduled_probe_count == 11
    assert config.dwell_ms == 120 and config.probe_ms == 20


def test_fixed_membership_is_64_chronological_physical_visits() -> None:
    cases = RUNNER._fixed_cases()
    assert len(cases) == 64
    assert {case.rate for case in cases} == set(RUNNER.dataset.RATES)
    assert all(case.origin == "recorded_development" for case in cases)
    assert all(case.visit_index is not None for case in cases)


def test_summary_reports_actual_routes_without_cache_claims() -> None:
    rows = [
        {
            "scientific_passed": False,
            "visit_outcome": "active_unassociated",
            "receiver_comparisons": [
                {
                    "outcome": "reference_positive_candidate_inactive",
                    "reference_active": True,
                    "candidate_active": False,
                },
                {"outcome": "extra", "reference_active": False, "candidate_active": True},
            ],
            "candidate": [{"route": "blind_cold"}, {"route": "blind_screen_disagreement"}],
        }
    ]
    summary = RUNNER.summarize(rows)
    assert summary["routes"] == {"blind_cold": 1, "blind_screen_disagreement": 1}
    assert summary["outcomes"] == {
        "extra": 1,
        "reference_positive_candidate_inactive": 1,
    }
    assert summary["visit_outcomes"] == {"active_unassociated": 1}
    assert summary["scientific_passed_rows"] == 0
