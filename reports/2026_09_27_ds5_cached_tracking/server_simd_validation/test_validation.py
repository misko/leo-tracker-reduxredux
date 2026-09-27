from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("server_simd_validation_runner", HERE / "run_validation.py")
assert SPEC and SPEC.loader
RUNNER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = RUNNER
SPEC.loader.exec_module(RUNNER)

from tools.presence_dwell import DwellResult  # noqa: E402
from tracking import Observation  # noqa: E402


def test_source_lock_and_unchanged_candidate() -> None:
    lock = RUNNER.verify_source_lock()
    assert lock["stage"] == "frozen_before_validation_outcomes"
    assert lock["outcome_informed_design"] is True
    assert lock["candidate_unchanged"] is True
    design = json.loads((HERE / "design.json").read_text())
    assert design["decision_context"]["original_component_gate_passed"] is False
    assert design["decision_context"]["candidate_changes_after_component_result"] == "none"


def test_fixed_inventory_excludes_holdout() -> None:
    cases = RUNNER.selected_cases()
    assert len(cases) == 160
    counts = {name: sum(inventory == name for inventory, *_ in cases) for name in {
        "new_development", "old_constructed_controls", "new_adversarial_controls"
    }}
    assert counts == {
        "new_development": 128,
        "old_constructed_controls": 12,
        "new_adversarial_controls": 20,
    }
    assert all(case["split"] in ("dev", "control") for _, _, case, _ in cases)


def test_science_signature_excludes_timing_but_keeps_detector_fields() -> None:
    first, second = DwellResult(), DwellResult()
    first.total_cpu_ms = 1.0
    second.total_cpu_ms = 9.0
    first.rank.fold_cpu_ms = 2.0
    second.rank.fold_cpu_ms = 8.0
    assert RUNNER.science_signature(first) == RUNNER.science_signature(second)
    second.rank.order[0] = 1
    assert RUNNER.science_signature(first) != RUNNER.science_signature(second)


def test_identity_counts_top_positive_mismatch_as_loss_and_extra() -> None:
    reference = Observation(0, 100.0, 1000.0, 0.2, 0.1, True)
    same = Observation(0, 101.0, 1500.0, 0.2, 0.1, True)
    other = Observation(0, 1000.0, 20_000.0, 0.2, 0.1, True)
    matched = RUNNER.identity(reference, same, 2_500_000)
    assert matched["matched_positive_reference"]
    mismatch = RUNNER.identity(reference, other, 2_500_000)
    assert mismatch["lost_positive_reference"]
    assert mismatch["additional_candidate_positive"]


def test_frozen_validation_result_is_complete_and_scientifically_exact() -> None:
    result = json.loads((HERE / "results.json").read_text())
    assert result["fresh_holdout_opened"] is False
    assert result["original_component_gate_passed"] is False
    assert result["candidate_unchanged_after_component_gate"] is True
    assert result["validation_gate_passed"] is True
    assert result["warmups_per_variant_receiver_case"] == 1
    assert result["repetitions"] == 3
    assert len(result["rows"]) == 320
    overall = result["summary"]["all"]
    assert overall["candidate_exact_fp32_mismatches"] == 0
    assert overall["repeatability_failures"] == 0
    assert overall["positive_counts"] == {
        "original_fp64_packed": 169,
        "stable_fp32_fftw": 169,
        "unchanged_server_simd": 169,
    }
    for comparison in ("stable_vs_original", "simd_vs_original"):
        assert overall[comparison] == {"lost": 0, "additional": 0, "matched": 169}


def test_reported_speedups_are_direct_timing_ratios() -> None:
    result = json.loads((HERE / "results.json").read_text())
    for summary in [
        result["summary"]["all"],
        *result["summary"]["by_inventory"].values(),
        *result["summary"]["by_rate_hz"].values(),
    ]:
        totals = summary["timing_totals_ms"]
        speedups = summary["speedups"]
        original = totals["original_fp64_packed"]
        stable = totals["stable_fp32_fftw"]
        simd = totals["unchanged_server_simd"]
        assert speedups["original_fp64_to_simd_cpu"] == original["cpu_ms"] / simd["cpu_ms"]
        assert speedups["original_fp64_to_simd_wall"] == original["wall_ms"] / simd["wall_ms"]
        assert speedups["stable_fp32_to_simd_cpu"] == stable["cpu_ms"] / simd["cpu_ms"]
        assert speedups["stable_fp32_to_simd_wall"] == stable["wall_ms"] / simd["wall_ms"]
