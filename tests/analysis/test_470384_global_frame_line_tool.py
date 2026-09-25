from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import numpy as np


def _tool() -> ModuleType:
    tools_root = Path(__file__).parents[2] / "tools"
    sys.path.insert(0, str(tools_root))
    path = tools_root / "report_470384_global_frame_line.py"
    spec = importlib.util.spec_from_file_location("report_470384_global_frame_line_tool", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _frames(
    tool: ModuleType,
    *,
    start_s: float,
    frame_count: int,
    intercept_hz: float,
    slope_hz_s: float,
    reference_time_s: float,
) -> tuple[object, ...]:
    output = []
    for index in range(frame_count):
        time_s = start_s + index * 0.0013332
        frequency_hz = intercept_hz + slope_hz_s * (time_s - reference_time_s)
        nco_hz = round(frequency_hz / 1_000.0) * 1_000.0
        residual_hz = frequency_hz - nco_hz
        exact = np.exp(-0.5 * ((tool.semicoherent.RESIDUAL_GRID_HZ - residual_hz) / 80.0) ** 2)
        control = np.full_like(exact, 0.02)
        output.append(
            tool.semicoherent.FrameLikelihood(
                time_s=time_s,
                nco_cfo_hz=nco_hz,
                even_exact_power=exact,
                even_exact_ceiling=1.0,
                even_control_power=control,
                even_control_ceiling=1.0,
                odd_exact_power=0.95 * exact,
                odd_exact_ceiling=1.0,
                odd_control_power=control,
                odd_control_ceiling=1.0,
            )
        )
    return tuple(output)


def test_global_line_recovers_shared_frequency_and_rate() -> None:
    tool = _tool()
    reference_time_s = 35.0
    frames = _frames(
        tool,
        start_s=33.7,
        frame_count=120,
        intercept_hz=420_123.0,
        slope_hz_s=-4_230.0,
        reference_time_s=reference_time_s,
    )
    fit_reference_s = float(np.mean([frame.time_s for frame in frames]))
    expected_frequency = 420_123.0 - 4_230.0 * (fit_reference_s - reference_time_s)

    result = tool.fit_global_line(
        frames,
        initial_frequency_hz=expected_frequency + 200.0,
        initial_slope_hz_s=-4_000.0,
    )

    assert abs(result.frequency_at_reference_hz - expected_frequency) <= 1.0
    assert abs(result.slope_hz_s + 4_230.0) <= 10.0
    assert result.validation_exact_control_db > 10.0


def test_probe_family_recovers_common_slope_with_varying_intercepts() -> None:
    tool = _tool()
    reference_time_s = 35.0
    slope_hz_s = -3_800.0
    groups = []
    for index, offset_hz in enumerate((-450.0, 250.0, -100.0, 500.0)):
        start_s = 34.0 + index * 0.2
        frames = _frames(
            tool,
            start_s=start_s,
            frame_count=15,
            intercept_hz=420_000.0 + offset_hz,
            slope_hz_s=slope_hz_s,
            reference_time_s=reference_time_s,
        )
        groups.append(
            (
                tool.semicoherent.Window(
                    association_index=index,
                    branch_index=3,
                    detection_time_s=start_s,
                    probe_sample_start=index * 50_000,
                    aligned_sample_start=index * 50_000,
                    local_epoch_sample=0,
                    initial_cfo_hz=420_000.0,
                    glrt_exact_score=0.5,
                    glrt_control_score=0.02,
                    glrt_margin=0.48,
                    selection_model_error_hz=0.0,
                ),
                frames,
            )
        )
    all_frames = tuple(frame for _window, frames in groups for frame in frames)
    global_fit = tool.fit_global_line(
        all_frames,
        initial_frequency_hz=423_000.0,
        initial_slope_hz_s=-3_800.0,
    )

    family, probes = tool.fit_probe_family(tuple(groups), global_fit=global_fit)

    assert abs(family.slope_hz_s - slope_hz_s) <= 100.0
    assert len(probes) == 4
    assert family.validation_exact_score > global_fit.validation_exact_score
