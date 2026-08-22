from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace


def _tool() -> ModuleType:
    path = Path(__file__).parents[2] / "tools" / "rerun_dense_independent_glrt.py"
    spec = importlib.util.spec_from_file_location("dense_independent_glrt_tool", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _row(tool: ModuleType, sample_start: int, time_s: float, rank: int, cfo_hz: float):
    return tool.CandidateRow(
        sample_start=sample_start,
        time_s=time_s,
        rank=rank,
        local_epoch_sample=10,
        acquired_cfo_hz=cfo_hz,
        tracking_cfo_hz=cfo_hz,
        residual_cfo_hz=0.0,
        exact_score=0.5,
        control_score=0.1,
        margin=0.4 - rank * 0.1,
        anchor_margin=0.2,
        symbolwise_margin=0.3,
        qam_accuracy=None,
    )


def test_summary_uses_every_probe_candidate_before_post_hoc_line_selection() -> None:
    tool = _tool()
    args = SimpleNamespace(
        session_id="capture",
        stream="stream-0",
        receiver=1,
        start_s=7.5,
        end_s=7.9,
        probe_ms=20.0,
        probe_spacing_ms=25.0,
        coarse_cfo_step_hz=10_000.0,
        fine_cfo_radius_hz=10_000.0,
        fine_cfo_step_hz=100.0,
        conditioned_cfo_radius_hz=1_000.0,
        conditioned_cfo_step_hz=25.0,
        candidate_count=32,
        candidate_cfo_separation_hz=10_000.0,
        candidate_epoch_separation_samples=5,
        glrt_size=4_096,
        line_rate_hz_s=0.0,
        line_intercept_hz=1_000.0,
        line_reference_s=0.0,
    )
    dense = (
        _row(tool, 100, 7.5, 0, 8_000.0),
        _row(tool, 100, 7.5, 1, 1_100.0),
        _row(tool, 200, 7.6, 0, 900.0),
        _row(tool, 200, 7.6, 1, -8_000.0),
    )

    result = tool._summarize(args, dense, dense, 1.0)

    assert result["dense"]["probe_count"] == 2
    assert result["dense"]["candidate_count"] == 4
    assert result["dense"]["focus_7_5_to_7_9"]["within_500_hz_probe_count"] == 2
    assert result["configuration"]["glrt_residual_spacing_hz"] < 56.0
    assert "no neighboring probe" in result["first_stage_independence"]


def test_candidate_only_metadata_persists_the_complete_search_configuration() -> None:
    tool = _tool()
    args = SimpleNamespace(
        session_id="capture",
        stream="stream-0",
        receiver=1,
        edge="lower",
        start_s=10.0,
        end_s=10.5,
        probe_ms=20.0,
        probe_spacing_ms=25.0,
        coarse_cfo_step_hz=1_000.0,
        fine_cfo_radius_hz=1_000.0,
        fine_cfo_step_hz=25.0,
        conditioned_cfo_radius_hz=500.0,
        conditioned_cfo_step_hz=10.0,
        candidate_count=32,
        candidate_cfo_separation_hz=500.0,
        candidate_epoch_separation_samples=5,
        glrt_size=4_096,
        workers=8,
    )
    config = SimpleNamespace(
        residual_cfo_min_hz=-400_000.0,
        residual_cfo_max_hz=400_000.0,
    )
    dense = (
        _row(tool, 100, 10.0, 0, 8_000.0),
        _row(tool, 100, 10.0, 1, 1_100.0),
        _row(tool, 200, 10.025, 0, 900.0),
    )

    result = tool._candidate_run_metadata(args, config, dense, 12.5)

    assert result["first_stage_independent"] is True
    assert result["probe_count"] == 2
    assert result["scored_candidate_count"] == 3
    assert result["coarse_cfo_step_hz"] == 1_000.0
    assert result["conditioned_cfo_step_hz"] == 10.0
    assert result["candidate_cfo_separation_hz"] == 500.0


def test_candidate_artifact_is_byte_reproducible(tmp_path: Path) -> None:
    tool = _tool()
    rows = (_row(tool, 100, 10.0, 0, 8_000.0),)
    first = tmp_path / "first.jsonl.gz"
    second = tmp_path / "second.jsonl.gz"

    tool._write_candidates(first, rows)
    tool._write_candidates(second, rows)

    assert first.read_bytes() == second.read_bytes()
