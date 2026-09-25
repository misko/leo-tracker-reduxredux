from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest


def _tool() -> ModuleType:
    path = Path(__file__).parents[2] / "tools" / "report_470384_sawtooth_methods.py"
    spec = importlib.util.spec_from_file_location("report_470384_sawtooth_methods_tool", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _observation(
    tool: ModuleType,
    row_index: int,
    time_s: float,
    cfo_hz: float,
    source_window_index: int,
    *,
    update: bool = True,
    exact_coherence: float = 0.12,
    coherence_margin: float = 0.10,
):
    return tool.FrameObservation(
        row_index=row_index,
        time_s=time_s,
        absolute_cfo_hz=cfo_hz,
        model_cfo_hz=0.0,
        source_window_index=source_window_index,
        exact_coherence=exact_coherence,
        coherence_margin=coherence_margin,
        frequency_uncertainty_hz=15.0,
        frequency_update_applied=update,
    )


def test_direct_quality_gate_keeps_online_rejected_frame() -> None:
    tool = _tool()
    gray = _observation(tool, 0, 1.0, 10_000.0, 0, update=False)
    bad_control = _observation(tool, 1, 1.1, 10_001.0, 0, coherence_margin=-0.01)

    assert tool.direct_quality_observations((gray, bad_control)) == (gray,)


def test_independent_lock_fit_recovers_local_doppler_rate() -> None:
    tool = _tool()
    observations = tuple(
        _observation(tool, index, 5.0 + index / 750, 20_000.0 - 3_800.0 * index / 750, 0)
        for index in range(15)
    )

    fits = tool.independent_lock_fits(observations)

    assert len(fits) == 1
    assert fits[0].slope_hz_s == pytest.approx(-3_800.0, abs=1e-6)
    assert fits[0].raw_rms_hz == pytest.approx(0.0, abs=1e-8)


def test_batch_joining_merges_continuous_locks_and_splits_cfo_jump() -> None:
    tool = _tool()
    observations = []
    row = 0
    rate_hz_s = -3_800.0
    for source, start_s, offset_hz in (
        (0, 1.000, 20_000.0),
        (1, 1.025, 20_000.0),
        (2, 1.050, 20_000.0),
        (3, 1.075, 20_300.0),
    ):
        for frame in range(15):
            time_s = start_s + frame / 750
            observations.append(
                _observation(
                    tool,
                    row,
                    time_s,
                    offset_hz + rate_hz_s * (time_s - 1.0),
                    source,
                    update=source != 1,
                )
            )
            row += 1
    values = tuple(observations)
    lock_fits = tool.independent_lock_fits(values)

    segments = tool.batch_joined_segments(
        values,
        lock_fits,
        noise_scale_hz=15.0,
        segment_penalty=15.0,
    )

    assert [(item.source_window_start, item.source_window_end) for item in segments] == [
        (0, 2),
        (3, 3),
    ]
    assert segments[0].frequency_update_count == 30
    assert segments[0].slope_hz_s == pytest.approx(rate_hz_s, abs=1e-6)


def test_joint_varying_intercept_fit_recovers_slope_progression() -> None:
    tool = _tool()
    observations = []
    row = 0
    reference_time_s = 10.5
    shared_slope_hz_s = -3_800.0
    progression_hz_s2 = 120.0
    for source in range(6):
        center = 10.0 + source * 0.2
        intercept = 40_000.0 + source * 173.0
        for frame in range(-15, 16):
            local_time = frame / 750
            time_s = center + local_time
            cfo = (
                intercept
                + shared_slope_hz_s * local_time
                + progression_hz_s2
                * ((center - reference_time_s) * local_time + 0.5 * local_time**2)
            )
            observations.append(_observation(tool, row, time_s, cfo, source))
            row += 1
    values = tuple(observations)
    segments = tool.independent_lock_fits(values)

    result = tool.joint_varying_intercept_fit(values, segments, slope_progression=True)

    assert result.reference_time_s == pytest.approx(reference_time_s)
    assert result.shared_slope_hz_s == pytest.approx(shared_slope_hz_s, abs=1e-5)
    assert result.slope_progression_hz_s2 == pytest.approx(progression_hz_s2, abs=1e-5)
    assert result.residual_rms_hz == pytest.approx(0.0, abs=1e-7)


def test_error_comparison_scores_same_frames_and_whole_probe_holdout(
    tmp_path: Path,
) -> None:
    tool = _tool()
    observations = []
    segments = []
    row = 0
    for segment_index in range(3):
        members = []
        center = 20.0 + segment_index * 0.4
        intercept = 50_000.0 + segment_index * 250.0
        for local_probe in range(2):
            probe = 2 * segment_index + local_probe
            probe_start = center - 0.024 + local_probe * 0.025
            for frame in range(15):
                time_s = probe_start + frame / 750
                noise_hz = 2.0 * ((row % 5) - 2)
                item = _observation(
                    tool,
                    row,
                    time_s,
                    intercept - 3_800.0 * (time_s - center) + noise_hz,
                    probe,
                )
                observations.append(item)
                members.append(item)
                row += 1
        segments.append(tool._fit_segment(members))
    values = tuple(observations)
    fitted_segments = tuple(item for item in segments if item is not None)
    common = tool.joint_varying_intercept_fit(
        values, fitted_segments, slope_progression=False
    )
    progression = tool.joint_varying_intercept_fit(
        values, fitted_segments, slope_progression=True
    )

    in_sample = tool.in_sample_model_error_comparison(
        values, fitted_segments, common, progression
    )
    probe_holdout = tool.leave_one_probe_out_model_error_comparison(
        values, fitted_segments
    )
    destination = tmp_path / "model-errors.png"
    tool.render_model_error_comparison(
        destination, in_sample, probe_holdout, progression
    )

    assert in_sample["overall"]["independent_ramp"]["frame_count"] == 90
    assert probe_holdout["overall"]["joint_common_slope"]["frame_count"] == 90
    assert probe_holdout["per_probe"]["joint_common_slope"]["probe_count"] == 6
    assert len(probe_holdout["probes"]) == 6
    assert destination.is_file()
    assert destination.stat().st_size > 0


def test_all_method_figures_render(tmp_path: Path) -> None:
    tool = _tool()
    observations = []
    row = 0
    for source in range(6):
        center = 35.60 + source * 0.025
        intercept = 425_000.0 + source * 15.0
        for frame in range(-7, 8):
            time_s = center + frame / 750
            observations.append(
                tool.FrameObservation(
                    row_index=row,
                    time_s=time_s,
                    absolute_cfo_hz=intercept - 3_800.0 * (time_s - center),
                    model_cfo_hz=425_000.0 - 7_000.0 * (time_s - 35.60),
                    source_window_index=source,
                    exact_coherence=0.12,
                    coherence_margin=0.10,
                    frequency_uncertainty_hz=15.0,
                    frequency_update_applied=row % 3 != 0,
                )
            )
            row += 1
    values = tuple(observations)
    lock_fits = tool.independent_lock_fits(values)
    partition = tool.batch_joined_segments(
        values,
        lock_fits,
        noise_scale_hz=18.0,
        segment_penalty=15.0,
    )
    coherent = tuple(item for item in partition if item.coherent)
    if len(coherent) < 3:
        coherent = lock_fits
    common = tool.joint_varying_intercept_fit(values, coherent, slope_progression=False)
    progression = tool.joint_varying_intercept_fit(values, coherent, slope_progression=True)
    destinations = (
        tmp_path / "method-1.png",
        tmp_path / "method-2.png",
        tmp_path / "method-3.png",
    )

    tool.render_method_1(destinations[0], values, lock_fits)
    tool.render_method_2(destinations[1], values, partition)
    tool.render_method_3(
        destinations[2],
        values,
        coherent,
        common,
        progression,
        common_loo_rms_hz_s=tool.slope_leave_one_segment_out_rms(coherent, linear=False),
        progression_loo_rms_hz_s=tool.slope_leave_one_segment_out_rms(
            coherent, linear=True
        ),
    )

    assert all(path.is_file() and path.stat().st_size > 0 for path in destinations)
