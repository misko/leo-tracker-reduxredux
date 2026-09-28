from __future__ import annotations

import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path

import pytest


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("ds7_progressive_evaluate", HERE / "evaluate.py")
evaluate_module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = evaluate_module
SPEC.loader.exec_module(evaluate_module)


def _context(visit: int, rate: int) -> dict[str, object]:
    return {
        "session_id": f"session-{rate}",
        "visit_index": visit,
        "manifest_sha256": "a" * 64,
        "sample_start_counter": visit * rate,
        "sample_end_counter": visit * rate + 10,
        "rate_hz": rate,
        "target_index": 4,
        "target": {"channel": 1, "edge": "upper", "rf_center_hz": 1, "if_center_hz": 1},
        "actual_lo_frequency_hz": 1,
        "actual_if_offset_hz": 0,
        "shape": [10, 2, 2],
        "dtype": "int16",
        "sha256": f"{visit:064x}",
    }


def _candidate(rank: int, epoch: int, margin: float) -> dict[str, object]:
    return {
        "candidate_rank": rank,
        "epoch_sample": epoch,
        "tracking_cfo_hz": 1_000.0,
        "exact_score": 0.2,
        "control_score": 0.1,
        "margin": margin,
        "passed_margin_gate": margin >= 0.025,
    }


def _result(*, sparse: bool) -> dict[str, object]:
    candidates = [_candidate(0, 100, 0.1)]
    if not sparse:
        candidates.append(_candidate(1, 200, 0.01))
    return {
        "first": None,
        "decision_best_margin": 0.1,
        "full_best_margin": 0.1,
        "reason": "synthetic",
        "probes": [
            {"receiver_id": 0, "probe_index": 0, "probe_start_ms": 0, "candidates": candidates},
            {"receiver_id": 0, "probe_index": 2, "probe_start_ms": 20, "candidates": candidates},
        ],
    }


def _row(context: dict[str, object], method: str, repeat: int) -> dict[str, object]:
    sparse = method == "sparse"
    return {
        "context": context,
        "method": method,
        "repeat": repeat,
        "status": "ok",
        "result": _result(sparse=sparse),
        "timing": {"cpu_s": 0.5 if sparse else 1.0, "wall_s": 0.6 if sparse else 1.2},
        "diagnostics": {
            "route": "sparse" if sparse else "full",
            "detector_calls": 1,
            "acquisition_calls": 4,
            "candidate_response_count": 2 if sparse else 4,
        },
    }


def _write_run(tmp_path: Path, *, mutate=None) -> tuple[Path, list[dict[str, object]]]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    cohort = [_context(1, 2_500_000), _context(2, 10_000_000)]
    methods = ["original", "optimized", "sparse"]
    rows = [_row(context, method, repeat) for repeat in (0, 1) for context in cohort for method in methods]
    if mutate is not None:
        mutate(rows)
    run = {
        "complete": True,
        "sources_unchanged": True,
        "failed_calls": 0,
        "repetitions": 2,
        "planned_calls": len(rows),
        "methods": ["original", "optimized", "sparse"],
        "source_hashes": {"methods_sparse.py": "b" * 64},
    }
    (tmp_path / "run.json").write_text(json.dumps(run))
    (tmp_path / "rows.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows))
    return tmp_path, cohort


def test_evaluate_keeps_repeat_zero_science_and_per_rate_gates(tmp_path):
    run, cohort = _write_run(tmp_path)
    result = evaluate_module.evaluate(run, expected_cohort=cohort, prior_directory=None)
    assert result["cohort"] == {
        "unique_visits": 2,
        "rate_visits": {"2500000": 1, "10000000": 1},
        "science_repeat": 0,
        "timing_repeats": [0, 1],
    }
    assert result["fresh_original_vs_prior_frozen"]["available"] is False
    sparse = result["methods"]["sparse"]
    assert sparse["repeatability_exact_result"] is True
    assert sparse["science"]["reference_denominators"]["negative_candidates"] == 4
    assert sparse["science"]["candidate_extras_unmatched_not_false_alarms"]["positive_candidates"] == 4
    assert sparse["development_recovery_gates"]["confirmation_recovery_at_least_90_percent"]
    assert sparse["development_recovery_gates"]["confirmation_recovery_at_least_80_percent"]
    assert sparse["by_rate"]["10000000"]["development_recovery_gates"]["confirmation_recovery_at_least_90_percent"]
    assert sparse["diagnostics"]["actual_candidate_response_counts_repeat0"]["total"] == 4
    assert sparse["candidate_confirmed_relative_to_reference_unconfirmed_not_false_alarms"]["added_on_reference_unconfirmed_receiver_visit_pairs"] == 0
    assert sparse["wall_speedup_vs_fresh_original"] == 2.0


def test_rejects_missing_repeat_visit_row(tmp_path):
    run, cohort = _write_run(tmp_path, mutate=lambda rows: rows.pop())
    with pytest.raises(ValueError, match="planned_calls|missing cohort"):
        evaluate_module.evaluate(run, expected_cohort=cohort, prior_directory=None)


def test_rejects_out_of_cohort_row_and_failed_receipt(tmp_path):
    def change_context(rows):
        rows[0]["context"] = _context(99, 7_500_000)
    run, cohort = _write_run(tmp_path, mutate=change_context)
    with pytest.raises(ValueError, match="outside"):
        evaluate_module.evaluate(run, expected_cohort=cohort, prior_directory=None)
    run, cohort = _write_run(tmp_path / "failed")
    receipt = json.loads((run / "run.json").read_text())
    receipt["failed_calls"] = 1
    (run / "run.json").write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match="failed"):
        evaluate_module.evaluate(run, expected_cohort=cohort, prior_directory=None)


def test_actual_frozen_cohort_has_the_expected_native_rate_mix():
    cohort = evaluate_module._default_cohort()
    identities = {evaluate_module._identity(context) for context in cohort}
    assert len(identities) == 28
    assert Counter(identity[5] for identity in identities) == {
        2_500_000: 16,
        5_000_000: 4,
        7_500_000: 4,
        10_000_000: 4,
    }
