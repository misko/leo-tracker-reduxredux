from __future__ import annotations

import csv
import hashlib
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2]
RESULT_ROOT = ROOT / "reports/figures/2026_08_25_polynomial_qin_injection"
REPORT = ROOT / "reports/2026_08_25_polynomial_qin_injection_results.md"
METRICS = RESULT_ROOT / "metrics.json"


def _result() -> dict[str, object]:
    value = json.loads(METRICS.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _digest(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def _csv_count(path: Path) -> int:
    with path.open(newline="", encoding="utf-8") as source:
        return sum(1 for _ in csv.DictReader(source))


def test_result_uses_only_frozen_background_spans_and_complete_scenario_ledger() -> None:
    result = _result()

    assert result["preregistration_commit"] == "5970769a34e40fde5d64ddf57b4be7fe2ac14d93"
    assert result["scenario_count"] == 18
    assert result["frame_row_count"] == 27_000
    assert result["cubic_row_count"] == 18
    assert [
        (row["session_id"], row["sample_start"], row["sample_count"]) for row in result["inputs"]
    ] == [
        ("cap-20260825T062228-886fe2dd9cde", 20_000_000, 5_000_000),
        ("cap-20260825T105640-facdadeffb3b", 55_000_000, 5_000_000),
        ("cap-20260825T111222-a2d4ce2afb9a", 90_000_000, 5_000_000),
    ]
    assert {row["status"] for row in result["capture_dispositions"]} == {"evaluable"}
    assert {row["scenario_id"] for row in result["frame_summaries"]} == {
        f"P{index:03d}" for index in range(1, 19)
    }


def test_result_retains_no_results_controls_and_failed_promotion() -> None:
    result = _result()
    promotion = result["promotion"]

    assert result["status"] == "fail"
    assert promotion["checks"]["all_three_backgrounds"] is False
    assert promotion["checks"]["fixed_500ms_rate_coverage_lower"] is False
    assert promotion["fixed_500ms"]["receiver_rmse"] == pytest.approx(163.314945788)
    assert promotion["fixed_500ms"]["receiver_coverage_95"] == pytest.approx(0.645083406497)
    assert promotion["fixed_500ms"]["no_result_scenario_count"] == 0

    no_step = {
        row["estimator"]: row for row in result["rate_aggregate"] if row["scope"] == "no_step"
    }
    assert no_step["causal_20ms_linear"]["no_result_scenario_count"] == 4
    assert no_step["fixed_125ms_linear"]["no_result_scenario_count"] == 4
    assert no_step["fixed_500ms_linear"]["no_result_scenario_count"] == 2
    assert sum(row["even_control_wins_occupied"] for row in result["frame_summaries"]) > 0
    assert sum(row["odd_control_wins_occupied"] for row in result["frame_summaries"]) > 0

    step = {(row["estimator"], row["phase"]): row for row in result["step_scenario_equal_metrics"]}
    assert step[("causal_20ms_linear", "transition")]["receiver_rmse"] == pytest.approx(4032.590282)
    assert step[("fixed_125ms_linear", "transition")]["receiver_rmse"] == pytest.approx(
        1264.93518254
    )
    assert step[("fixed_500ms_linear", "transition")]["receiver_rmse"] == pytest.approx(
        545.144454545
    )


def test_result_binds_corrective_execution_without_overwriting_it() -> None:
    result = _result()

    assert result["repository_head_at_execution"] == "bdb9af106568669fb794de23e44e6008b3006fe1"
    assert result["execution_authority"]["implementation_commit"] == (
        "49b33b900e9bb65186fa014675811764245b3b22"
    )
    assert result["implementation"]["tool_sha256"] == _digest(
        ROOT / "tools/run_polynomial_qin_injection.py"
    )
    assert result["implementation"]["kernel_sha256"] == _digest(
        ROOT / "src/leo/analysis/research/polynomial_injection.py"
    )
    assert "postprocess_implementation" not in result


def test_clock_factor_is_labeled_as_phase_coordinate_only() -> None:
    scope = _result()["sample_clock_factor_implementation"]

    assert scope == {
        "scope": "phase_coordinate_scale_only",
        "phase_polynomial_time_warped": True,
        "qin_waveform_resampled": False,
        "frame_lattice_resampled": False,
        "interpretation": (
            "not a full sample-clock or timing-offset simulation; fixed 3333/3334-sample "
            "frame boundaries are unchanged"
        ),
    }


def test_sealed_row_counts_hashes_and_report_links_resolve() -> None:
    result = _result()
    assert _csv_count(RESULT_ROOT / "frame-evidence.csv") == 27_000
    assert _csv_count(RESULT_ROOT / "rate-estimates.csv") == result["rate_row_count"]
    assert _csv_count(RESULT_ROOT / "cubic-estimates.csv") == 18
    assert _csv_count(RESULT_ROOT / "scenario-summary.csv") == 18

    for name, expected in result["artifacts"].items():
        path = REPORT if name == REPORT.name else RESULT_ROOT / name
        assert path.is_file()
        assert _digest(path) == expected

    text = REPORT.read_text(encoding="utf-8")
    links = re.findall(r"!\[[^]]*\]\(([^)]+\.png)\)", text)
    assert len(links) == 5
    assert all((REPORT.parent / link).is_file() for link in links)
    assert re.search(r"phase-coordinate\s+clock-scale test", text)
    assert "not a full sample-clock or timing-offset simulation" in text
