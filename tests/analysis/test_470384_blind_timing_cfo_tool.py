from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType


def _tool() -> ModuleType:
    tools_root = Path(__file__).parents[2] / "tools"
    sys.path.insert(0, str(tools_root))
    path = tools_root / "report_470384_blind_timing_cfo.py"
    spec = importlib.util.spec_from_file_location("report_470384_blind_timing_cfo_tool", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _candidate(tool: ModuleType, cell: int, time_s: float, epoch: int, cfo: float, margin: float):
    return tool.BlindCandidate(
        cell_index=cell,
        cell_start_s=time_s - 0.006,
        cell_center_s=time_s,
        refined_epoch_sample=epoch,
        absolute_frame_start_sample=cell * 10_000 + epoch,
        absolute_cfo_hz=cfo,
        acquire_score=margin + 0.05,
        verify_score=margin + 0.04,
        control_score=0.01,
        margin=margin,
        frame_support=8,
    )


def test_deduplicate_keeps_strongest_matching_basin() -> None:
    tool = _tool()
    weak = _candidate(tool, 0, 35.0, 100, 420_000.0, 0.1)
    strong = _candidate(tool, 0, 35.0, 104, 420_500.0, 0.3)
    other = _candidate(tool, 0, 35.0, 500, 426_000.0, 0.2)

    result = tool._deduplicate([weak, strong, other])

    assert strong in result
    assert weak not in result
    assert other in result


def test_latent_line_recovers_one_mode_while_retaining_distractors() -> None:
    tool = _tool()
    candidates = []
    reference = 35.0
    for cell in range(600):
        time_s = 33.8 + cell * 0.004
        true_cfo = 430_000.0 - 4_000.0 * (time_s - reference)
        candidates.append(_candidate(tool, cell, time_s, 300, true_cfo, 0.3))
        candidates.append(_candidate(tool, cell, time_s, 1_700, true_cfo + 7_000.0, 0.2))

    line, selected = tool.fit_latent_line(tuple(candidates), label="primary", seed=8)

    expected = 430_000.0 - 4_000.0 * (line.reference_time_s - reference)
    assert abs(line.frequency_at_reference_hz - expected) < 1.0
    assert abs(line.slope_hz_s + 4_000.0) < 1.0
    assert len(selected) == 600


def test_segment_path_splits_timing_modes_and_fits_each_local_line() -> None:
    tool = _tool()
    candidates = []
    for cell in range(12):
        time_s = 35.0 + cell * 0.004
        epoch = 300 if cell < 6 else 900
        slope = -3_000.0 if cell < 6 else -4_000.0
        frequency = 430_000.0 + slope * (time_s - 35.0)
        candidates.append(_candidate(tool, cell, time_s, epoch, frequency, 0.3))

    segments = tool.segment_path(tuple(candidates))

    assert len(segments) == 2
    assert segments[0].preceding_boundary_time_s is None
    assert abs(segments[1].preceding_boundary_time_s - 35.022) < 1e-12
    assert abs(segments[0].slope_hz_s + 3_000.0) < 1e-6
    assert abs(segments[1].slope_hz_s + 4_000.0) < 1e-6
    assert segments[0].rms_hz < 1e-8
    assert segments[1].rms_hz < 1e-8
