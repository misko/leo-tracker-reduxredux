from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType


def _tool() -> ModuleType:
    path = (
        Path(__file__).parents[2]
        / "tools"
        / "report_t1_glrt_search_parameter_study.py"
    )
    spec = importlib.util.spec_from_file_location("t1_glrt_parameter_study", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _row(tool: ModuleType, time_s: float, rank: int, cfo_hz: float, margin: float):
    return tool.CandidateRow(
        sample_start=round(time_s * 1_000),
        time_s=time_s,
        rank=rank,
        local_epoch_sample=10,
        acquired_cfo_hz=cfo_hz,
        tracking_cfo_hz=cfo_hz,
        residual_cfo_hz=0.0,
        exact_score=margin + 0.1,
        control_score=0.1,
        margin=margin,
        anchor_margin=0.1,
        symbolwise_margin=0.1,
        qam_accuracy=None,
    )


def test_piecewise_reference_switches_at_declared_transition() -> None:
    tool = _tool()
    lines = (
        {"interval_s": [0.0, 1.0], "slope_hz_s": -10.0, "intercept_hz": 100.0},
        {"interval_s": [1.0, 2.0], "slope_hz_s": -20.0, "intercept_hz": 80.0},
    )

    assert tool.expected_frequency(lines, 0.5) == 95.0
    assert tool.expected_frequency(lines, 1.5) == 50.0


def test_summary_separates_winner_from_retained_inventory() -> None:
    tool = _tool()
    lines = (
        {"interval_s": [0.0, 2.0], "slope_hz_s": 0.0, "intercept_hz": 1_000.0},
    )
    rows = (
        _row(tool, 0.0, 0, 30_000.0, 0.4),
        _row(tool, 0.0, 1, 1_100.0, 0.3),
        _row(tool, 1.0, 0, 950.0, 0.2),
        _row(tool, 1.0, 1, -30_000.0, 0.1),
    )

    result = tool.summarize_population(rows, lines, start_s=0.0, end_s=2.0)

    assert result["probe_count"] == 2
    assert result["winner_hit_count"] == 1
    assert result["inventory_hit_count"] == 2
    assert result["median_selected_rank"] == 0.5


def test_study_profiles_include_one_factor_and_combined_controls() -> None:
    tool = _tool()
    profiles = {item.key: item for item in tool.PROFILES}

    assert profiles["standard"].candidate_count == 8
    assert profiles["basins"].candidate_count == 32
    assert profiles["basins"].coarse_step_hz == profiles["standard"].coarse_step_hz
    assert profiles["glrt"].glrt_size == 4_096
    assert profiles["full_dense"].candidate_count == 32
    assert profiles["full_dense"].coarse_step_hz == 10_000.0


def test_full_capture_cost_sweep_declares_recommendation_and_budget_boundary() -> None:
    tool = _tool()
    sweep = tool._load_cost_sweep(tool.DEFAULT_COST_SWEEP)
    profiles = {item["key"]: item for item in sweep["profiles"]}

    assert profiles["standard"]["inventory_hits"] == 826
    assert profiles["recommended"]["candidate_cfo_separation_hz"] == 70_000.0
    assert profiles["recommended"]["candidate_epoch_separation_samples"] == 5
    assert profiles["recommended"]["inventory_hits"] == 856
    assert profiles["count9"]["process_cpu_s"] < 1.1 * profiles["standard"]["process_cpu_s"]
    assert profiles["count10"]["process_cpu_s"] > 1.1 * profiles["standard"]["process_cpu_s"]
    assert sweep["dense_increment_definition"]["ninety_percent_increment_target_hits"] == 875
