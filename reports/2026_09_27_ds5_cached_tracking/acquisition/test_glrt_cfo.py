from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("glrt_cfo_oracle", HERE / "run_glrt_cfo_oracle.py")
assert SPEC and SPEC.loader
oracle = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = oracle
SPEC.loader.exec_module(oracle)


def test_design_has_only_two_fixed_center_banks() -> None:
    design = json.loads((HERE / "glrt_cfo_design.json").read_text())
    assert design["variants"] == [
        {
            "name": "four_centers",
            "centers_hz": [-300000, -100000, 100000, 300000],
        },
        {
            "name": "eight_centers",
            "centers_hz": [
                -350000,
                -250000,
                -150000,
                -50000,
                50000,
                150000,
                250000,
                350000,
            ],
        },
    ]


def test_inputs_are_hash_pinned_and_reference_is_development_only() -> None:
    design = json.loads((HERE / "glrt_cfo_design.json").read_text())
    reference = oracle.load_json(HERE / "results.json", design["reference_results_sha256"])
    assert reference["fresh_holdout_opened"] is False
    positives = [row for row in reference["rows"] if row["reference"]["positive"]]
    assert len(positives) == 36
    dataset = oracle.load_json(oracle.DATASET / "cases.json", design["dataset_cases_sha256"])
    cases = {case["case_id"]: case for case in dataset["cases"]}
    assert all(cases[row["case_id"]]["split"] == "dev" for row in positives)


def test_control_inventory_is_fixed_and_not_a_center_input() -> None:
    design = json.loads((HERE / "glrt_cfo_design.json").read_text())
    payload = oracle.load_json(
        oracle.CONTROL_DATASET / "cases.json", design["control_cases_sha256"]
    )
    controls = [
        case
        for case in payload["cases"]
        if case["origin"] == "synthetic_control" and case["rate_hz"] in (2_500_000, 5_000_000)
    ]
    assert len(controls) == 12
    assert {case["truth"]["kind"] for case in controls} == {
        "pilot",
        "noise",
        "tone",
    }


def test_frozen_result_is_development_only_and_source_aligned() -> None:
    path = HERE / "glrt_cfo_results.json"
    assert oracle.digest(path) == (
        "sha256:414271b5ecffcdb2a43f91196c50d7bf7a01eef28127c01dd35e56f85581b80e"
    )
    result = json.loads(path.read_text())
    assert result["fresh_holdout_opened"] is False
    assert len(result["rows"]) == 36
    assert len(result["control_rows"]) == 24

    design = json.loads((HERE / "glrt_cfo_design.json").read_text())
    dataset = oracle.load_json(oracle.DATASET / "cases.json", design["dataset_cases_sha256"])
    development = {case["case_id"]: case for case in dataset["cases"] if case["split"] == "dev"}
    for row in result["rows"]:
        case = development[row["case_id"]]
        assert row["source_start_counter"] == case["source_start_counter"]
        assert case["split"] == "dev"
