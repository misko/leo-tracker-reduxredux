from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import numpy as np


def _tool() -> ModuleType:
    tools_root = Path(__file__).parents[2] / "tools"
    sys.path.insert(0, str(tools_root))
    path = tools_root / "report_470384_joint_frame_surface.py"
    spec = importlib.util.spec_from_file_location("report_470384_joint_frame_surface_tool", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _frames(tool: ModuleType) -> tuple[object, ...]:
    reference_time_s = 35.0
    frames = []
    for index in range(100):
        time_s = 34.0 + index * 0.02
        frequency_hz = 425_137.0 - 4_370.0 * (time_s - reference_time_s)
        nco_hz = round(frequency_hz / 2_000.0) * 2_000.0
        residual_hz = frequency_hz - nco_hz
        exact = np.exp(-0.5 * ((tool.semicoherent.RESIDUAL_GRID_HZ - residual_hz) / 70.0) ** 2)
        control = np.full_like(exact, 0.02)
        frames.append(
            tool.semicoherent.FrameLikelihood(
                time_s=time_s,
                nco_cfo_hz=nco_hz,
                even_exact_power=exact,
                even_exact_ceiling=1.0,
                even_control_power=control,
                even_control_ceiling=1.0,
                odd_exact_power=0.96 * exact,
                odd_exact_ceiling=1.0,
                odd_control_power=control,
                odd_control_ceiling=1.0,
            )
        )
    return tuple(frames)


def test_unseeded_joint_search_recovers_line_across_varying_local_ncos() -> None:
    tool = _tool()
    frames = _frames(tool)
    fit_reference_s = float(np.mean([frame.time_s for frame in frames]))
    expected_frequency = 425_137.0 - 4_370.0 * (fit_reference_s - 35.0)

    result = tool.fit_joint_line(
        frames,
        frequency_bounds_hz=(415_000.0, 435_000.0),
        slope_bounds_hz_s=(-10_000.0, 1_000.0),
        coarse_frequency_step_hz=100.0,
        coarse_slope_step_hz_s=250.0,
    )

    assert abs(result.fit.frequency_at_reference_hz - expected_frequency) <= 1.0
    assert abs(result.fit.slope_hz_s + 4_370.0) <= 10.0
    assert result.frame_coverage_fraction == 1.0


def test_joint_surface_uses_every_frame_in_one_weighted_objective() -> None:
    tool = _tool()
    frames = _frames(tool)
    reference_time_s = float(np.mean([frame.time_s for frame in frames]))
    surface = tool.score_surface(
        frames,
        reference_time_s=reference_time_s,
        intercepts_hz=np.asarray([420_000.0, 425_000.0, 430_000.0]),
        slopes_hz_s=np.asarray([-8_000.0, -4_000.0, 0.0]),
        split="even",
    )

    assert surface.shape == (3, 3)
    assert np.unravel_index(int(np.argmax(surface)), surface.shape) == (1, 1)
