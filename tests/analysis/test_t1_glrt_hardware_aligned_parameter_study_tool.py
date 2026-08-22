from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType


def _tool() -> ModuleType:
    tool_name = "report_t1_glrt_hardware_aligned_parameter_study.py"
    path = Path(__file__).parents[2] / "tools" / tool_name
    spec = importlib.util.spec_from_file_location("t1_glrt_hardware_study", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _row(tool: ModuleType, rank: int, cfo_hz: float, *, epoch: int = 10):
    return tool.CandidateRow(
        sample_start=1_000,
        time_s=1.0,
        rank=rank,
        local_epoch_sample=epoch,
        acquired_cfo_hz=cfo_hz,
        tracking_cfo_hz=cfo_hz,
        residual_cfo_hz=0.0,
        exact_score=0.3,
        control_score=0.1,
        margin=0.2,
        anchor_margin=0.1,
        symbolwise_margin=0.1,
        qam_accuracy=None,
    )


def test_profiles_preserve_lane_parameters_around_only_fine_grid_change() -> None:
    tool = _tool()
    profiles = {profile.key: profile for profile in tool.PROFILES}

    assert profiles["standard_current"].candidate_count == 10
    assert profiles["standard_current"].glrt_size == 512
    assert profiles["standard_aligned"].fine_step_hz == 2_500_000 / 4_096
    assert tool._nominal_fine_bins(profiles["standard_aligned"]) == 263
    assert profiles["research_current"].candidate_count == 32
    assert profiles["research_current"].glrt_size == 4_096
    assert profiles["research_aligned"].fine_step_hz == 2_500_000 / 16_384
    assert tool._nominal_fine_bins(profiles["research_aligned"]) == 133
    assert profiles["research_aligned"].conditioned_step_hz == (
        profiles["research_current"].conditioned_step_hz
    )


def test_scientific_delta_separates_epoch_and_numeric_changes() -> None:
    tool = _tool()
    reference = (_row(tool, 0, 1_000.0), _row(tool, 1, 2_000.0))
    candidate = (_row(tool, 0, 1_010.0, epoch=11), _row(tool, 1, 2_020.0))

    delta = tool._scientific_delta(reference, candidate)

    assert delta["matched_basin_count"] == 1
    assert delta["unmatched_reference_basin_count"] == 1
    assert delta["common_probe_count"] == 1
    assert delta["winner_epoch_change_count"] == 1
    assert delta["maximum_absolute_acquired_cfo_delta_hz"] == 20.0
    assert delta["maximum_absolute_winner_cfo_delta_hz"] == 10.0
