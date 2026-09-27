from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("cached_acquisition", HERE / "run_acquisition.py")
assert SPEC and SPEC.loader
acquisition = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = acquisition
SPEC.loader.exec_module(acquisition)


def test_frozen_inputs_and_development_only_selection() -> None:
    design = json.loads((HERE / "design_variants.json").read_text())
    payload = acquisition.load_json(
        acquisition.DATASET / "cases.json", design["dataset_cases_sha256"]
    )
    selected = acquisition.select_development(payload)
    assert len(selected) == 128
    assert all(case["split"] == "dev" for case in selected)
    assert {case["rate_hz"] for case in selected} == set(acquisition.RATES)
    assert not {case["case_id"] for case in selected} & {
        case["case_id"] for case in payload["cases"] if case["split"] == "holdout"
    }


def test_fixed_control_inventory() -> None:
    design = json.loads((HERE / "design_variants.json").read_text())
    payload = acquisition.load_json(
        acquisition.CONTROL_DATASET / "cases.json", design["control_cases_sha256"]
    )
    controls = acquisition.select_controls(payload)
    assert len(controls) == 12
    assert {case["truth"]["kind"] for case in controls} == {
        "pilot",
        "noise",
        "tone",
    }
    assert len({case["raw_npy"]["sha256"] for case in controls}) == 12


def test_positive_gate_is_strict_and_requires_fractional_complete() -> None:
    equal = acquisition.Observation(0, 1.0, 0.0, 0.125, 0.1, True)
    above = acquisition.Observation(0, 1.0, 0.0, 0.1250001, 0.1, True)
    incomplete = acquisition.Observation(0, 1.0, 0.0, 1.0, 0.0, False)
    assert not equal.positive
    assert above.positive
    assert not incomplete.positive


def test_summary_counts_losses_extras_and_full_cost() -> None:
    def row(reference: bool, candidate: bool, matched: bool) -> dict:
        return {
            "reference": {
                "positive": reference,
            },
            "candidate": {
                "positive": candidate,
                "candidate_count": 1,
                "fractional_complete": candidate,
            },
            "matched_reference": matched,
            "baseline_timing": {"cpu_ms": 2.0, "wall_ms": 3.0},
            "candidate_timing": {"cpu_ms": 1.0, "wall_ms": 1.5},
        }

    summary = acquisition.summarize(
        [row(True, True, True), row(True, False, False), row(False, True, False)]
    )
    assert summary["reference_positives"] == 2
    assert summary["matched_reference_positives"] == 1
    assert summary["lost_reference_positives"] == 1
    assert summary["additional_candidate_positives"] == 1
    assert summary["costs"]["cpu_speedup"] == 2.0


def test_missing_library_is_rejected() -> None:
    with pytest.raises(FileNotFoundError):
        acquisition.run(HERE / "does-not-exist.so")


@pytest.mark.parametrize(
    ("name", "expected_sha256", "expected_seeded"),
    [
        (
            "results.json",
            "sha256:6e6934137b2a76e7e697c94eaeb6c6faf71a3fde94c43e894cbc3192e040c518",
            True,
        ),
        (
            "results_fft32.json",
            "sha256:2bebc5de8e419e3a98a547d08343a66e49a3c5f08e1da81271bf0bd8d87a1783",
            False,
        ),
        (
            "results_fft32_fftw.json",
            "sha256:ce5474d2060a727c44bf9ec528b5d35d957544dd3d033a1d503e906c7a738c57",
            False,
        ),
    ],
)
def test_receipts_are_development_only_and_source_aligned(
    name: str, expected_sha256: str, expected_seeded: bool
) -> None:
    path = HERE / name
    assert acquisition.digest(path) == expected_sha256
    result = json.loads(path.read_text())
    assert result["fresh_holdout_opened"] is False
    assert result["candidate_seeded"] is expected_seeded

    variant_design = json.loads((HERE / "design_variants.json").read_text())
    payload = acquisition.load_json(
        acquisition.DATASET / "cases.json", variant_design["dataset_cases_sha256"]
    )
    development = {case["case_id"]: case for case in acquisition.select_development(payload)}
    assert len(result["rows"]) == 256
    assert {row["case_id"] for row in result["rows"]} == set(development)
    for row in result["rows"]:
        case = development[row["case_id"]]
        assert case["split"] == "dev"
        assert row["source_start_counter"] == case["source_start_counter"]

    control_payload = acquisition.load_json(
        acquisition.CONTROL_DATASET / "cases.json",
        variant_design["control_cases_sha256"],
    )
    controls = {case["case_id"] for case in acquisition.select_controls(control_payload)}
    assert len(result["control_rows"]) == 24
    assert {row["case_id"] for row in result["control_rows"]} == controls
