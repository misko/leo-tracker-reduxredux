from __future__ import annotations

import importlib.util
import sys
from dataclasses import replace
from pathlib import Path
from types import ModuleType

import numpy as np


def _tool() -> ModuleType:
    tools_root = Path(__file__).parents[2] / "tools"
    sys.path.insert(0, str(tools_root))
    try:
        path = tools_root / "report_d3_d4_underlying_rates.py"
        spec = importlib.util.spec_from_file_location(
            "report_d3_d4_underlying_rates_tool", path
        )
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(tools_root))
    return module


def _observations_and_segments(tool: ModuleType) -> tuple[tuple[object, ...], tuple[object, ...]]:
    observations = []
    segments = []
    row_index = 0
    slope = -4_000.0
    for segment_index, center in enumerate((1.0, 2.0, 3.0, 4.0)):
        indexes = []
        times = center + np.linspace(-0.04, 0.04, 31)
        for time_s in times:
            indexes.append(row_index)
            observations.append(
                tool.rate_tool.FrameObservation(
                    row_index=row_index,
                    time_s=float(time_s),
                    absolute_cfo_hz=float(100_000.0 * segment_index + slope * (time_s - center)),
                    model_cfo_hz=0.0,
                    source_window_index=segment_index,
                    exact_coherence=0.8,
                    coherence_margin=0.7,
                    frequency_uncertainty_hz=25.0,
                    frequency_update_applied=False,
                )
            )
            row_index += 1
        segments.append(
            tool.rate_tool.SegmentFit(
                source_window_start=segment_index,
                source_window_end=segment_index,
                observation_indices=tuple(indexes),
                frame_count=len(indexes),
                frequency_update_count=0,
                start_time_s=float(times[0]),
                end_time_s=float(times[-1]),
                center_time_s=center,
                intercept_hz=100_000.0 * segment_index,
                slope_hz_s=slope,
                slope_sigma_hz_s=100.0,
                robust_rms_hz=0.0,
                raw_rms_hz=0.0,
                held_out_rms_hz=0.0,
            )
        )
    return tuple(observations), tuple(segments)


def test_varying_intercept_slope_ignores_segment_offsets() -> None:
    tool = _tool()
    observations, segments = _observations_and_segments(tool)

    slope = tool.ordinary_varying_intercept_slope(observations, segments)

    assert np.isclose(slope, -4_000.0)


def test_cluster_bootstrap_recovers_deterministic_slope() -> None:
    tool = _tool()
    observations, segments = _observations_and_segments(tool)

    result = tool.ramp_cluster_bootstrap(
        observations,
        segments,
        primary_slope_hz_s=-4_000.0,
        seed=7,
        replicates=500,
    )

    assert np.isclose(result["ordinary_full_sample_hz_s"], -4_000.0)
    assert result["standard_error_hz_s"] < 1e-8
    assert np.isclose(result["p50_hz_s"], -4_000.0)


def test_random_effects_mean_and_uncertainty() -> None:
    tool = _tool()
    _observations, segments = _observations_and_segments(tool)
    varied = tuple(
        replace(segment, slope_hz_s=slope)
        for segment, slope in zip(
            segments,
            (-4_300.0, -4_100.0, -3_900.0, -3_700.0),
            strict=True,
        )
    )

    result = tool.random_effects_slope(varied)

    assert np.isclose(result["mean_hz_s"], -4_000.0)
    assert result["standard_error_hz_s"] > 0.0
    assert result["between_ramp_sigma_hz_s"] > 0.0
