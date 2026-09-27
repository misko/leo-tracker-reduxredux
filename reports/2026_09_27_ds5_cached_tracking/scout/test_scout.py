from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pytest

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("cached_scout", HERE / "run_scout.py")
assert SPEC and SPEC.loader
scout = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = scout
SPEC.loader.exec_module(scout)


def test_reference_gate_and_source_counter_inventory() -> None:
    design = json.loads((HERE / "design.json").read_text())
    reference = scout.load_json(scout.REFERENCE, design["reference_results_sha256"])
    rows = scout.load_reference(reference)
    assert len(rows) == 256
    assert sum(row["reference_positive"] for row in rows.values()) == 36
    dataset = scout.load_json(scout.DATASET / "cases.json", design["dataset_cases_sha256"])
    cases = scout.select_cases(dataset, "dev")
    for case in cases:
        for rx in range(2):
            row = rows[(case["case_id"], rx)]
            assert row["start_counter"] == case["source_start_counter"]
            assert row["end_counter"] == case["source_end_counter_exclusive"]


def test_threshold_is_inclusive_and_retains_all_reference_positives() -> None:
    rows = [{"reference_positive": True, "score": float(index + 1)} for index in range(36)] + [
        {"reference_positive": False, "score": 0.5}
    ]
    threshold = scout.threshold_for_full_retention(rows, "score")
    assert threshold == 1.0
    summary_rows = [
        {
            **row,
            "rate_hz": 2_500_000,
            "baseline_cpu_ms": 1.0,
            "screen_cpu_ms": 0.01,
        }
        for row in rows
    ]
    summary = scout.summarize_variant(summary_rows, "score", threshold, "screen_cpu_ms")
    assert summary["retained_reference_positives"] == 36
    assert summary["reference_relative_retention"] == 1.0


def test_controls_are_fixed_prior_arrays_and_not_threshold_inputs() -> None:
    design = json.loads((HERE / "design.json").read_text())
    payload = scout.load_json(scout.CONTROL_DATASET / "cases.json", design["control_cases_sha256"])
    cases = scout.select_cases(payload, "control", controls=True)
    assert len(cases) == 12
    assert {case["rate_hz"] for case in cases} == {2_500_000, 5_000_000}
    assert {case["truth"]["kind"] for case in cases} == {"pilot", "noise", "tone"}
    assert len({case["raw_npy"]["sha256"] for case in cases}) == 12


def test_threshold_rejects_missing_positive_inventory() -> None:
    with pytest.raises(ValueError, match="all 36"):
        scout.threshold_for_full_retention([{"reference_positive": True, "score": 1.0}], "score")


@pytest.mark.parametrize("rate", scout.RATES)
def test_sparse_scout_null_noise_and_tone(rate: int) -> None:
    native = scout.SparseScout(scout.ensure_sparse_library(), rate)
    count = rate * 120 // 1000
    zeros = np.zeros((count, 2), dtype="<i2")
    null = native.run(zeros)
    assert null.power_sum_score == 0.0
    assert null.pairs_per_window == 5000

    rng = np.random.default_rng(rate)
    noise = rng.integers(-1000, 1001, (count, 2), dtype=np.int16)
    noise_score = native.run(noise).power_sum_score
    assert 0.0 <= noise_score < 0.1

    phase = 2 * np.pi * 17_000 * np.arange(count) / rate
    tone = np.column_stack((np.cos(phase), np.sin(phase)))
    tone = np.rint(tone * 1000).astype("<i2")
    assert native.run(tone).power_sum_score > 0.99


def test_frozen_results_have_only_development_and_fixed_controls() -> None:
    results_path = HERE / "results.json"
    results = json.loads(results_path.read_text())
    assert scout.digest(results_path) == (
        "sha256:e21e363e28dba103c9336fad411b59c71700282647ef9089d9b18b9821795e18"
    )
    design = json.loads((HERE / "design.json").read_text())
    dataset = scout.load_json(scout.DATASET / "cases.json", design["dataset_cases_sha256"])
    development = {case["case_id"]: case for case in scout.select_cases(dataset, "dev")}
    assert {row["case_id"] for row in results["rows"]} == set(development)
    assert len(results["rows"]) == 256
    for row in results["rows"]:
        case = development[row["case_id"]]
        assert row["source_start_counter"] == case["source_start_counter"]
        assert case["split"] == "dev"

    controls = scout.load_json(scout.CONTROL_DATASET / "cases.json", design["control_cases_sha256"])
    allowed_controls = {
        case["case_id"] for case in scout.select_cases(controls, "control", controls=True)
    }
    assert {row["case_id"] for row in results["control_rows"]} == allowed_controls
