from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np


def _tool():
    path = Path(__file__).parents[2] / "tools" / "report_470384_semicoherent_recovery.py"
    spec = importlib.util.spec_from_file_location("report_470384_semicoherent_recovery", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_normalized_frequency_curves_peak_at_injected_residual() -> None:
    tool = _tool()
    symbol_times = np.arange(300, dtype=float) / 234_375.0
    times = np.stack([symbol_times + frame / 750.0 for frame in range(4)])
    residual_hz = 725.0
    phases = np.asarray([0.2, -1.3, 2.1, 0.8])
    values = np.exp(
        1j
        * (
            phases[:, None]
            + 2 * np.pi * residual_hz * (times - np.mean(times, axis=1, keepdims=True))
        )
    )

    power, ceiling = tool.normalized_frequency_curves(
        values,
        times,
        np.arange(0, 300, 2),
    )

    peaks = tool.RESIDUAL_GRID_HZ[np.argmax(power, axis=1)]
    assert np.all(np.abs(peaks - residual_hz) <= 25.0)
    assert np.allclose(ceiling, 150.0**2)


def _synthetic_frame(tool, *, time_s: float, nco_hz: float, peak_hz: float):
    width_hz = 240.0
    exact = np.exp(-0.5 * ((tool.RESIDUAL_GRID_HZ - peak_hz) / width_hz) ** 2)
    control = np.full_like(exact, 0.01)
    return tool.FrameLikelihood(
        time_s=time_s,
        nco_cfo_hz=nco_hz,
        even_exact_power=exact,
        even_exact_ceiling=1.0,
        even_control_power=control,
        even_control_ceiling=1.0,
        odd_exact_power=exact,
        odd_exact_ceiling=1.0,
        odd_control_power=control,
        odd_control_ceiling=1.0,
    )


def test_likelihood_line_fit_recovers_frequency_and_rate_with_frame_phase_removed() -> None:
    tool = _tool()
    reference_time_s = 30.0
    true_frequency_hz = 250_400.0
    true_slope_hz_s = -3_500.0
    nco_hz = 250_000.0
    times = np.linspace(29.96, 30.04, 48)
    frames = tuple(
        _synthetic_frame(
            tool,
            time_s=float(time_s),
            nco_hz=nco_hz,
            peak_hz=true_frequency_hz + true_slope_hz_s * (time_s - reference_time_s) - nco_hz,
        )
        for time_s in times
    )
    branch = tool.Branch(
        index=0,
        label="synthetic",
        start_s=29.9,
        end_s=30.1,
        reference_time_s=reference_time_s,
        coefficients_hz=(250_000.0,),
    )

    fit = tool.fit_likelihood_line(frames, branch=branch, split="even")

    assert abs(fit.frequency_at_reference_hz - true_frequency_hz) <= 25.0
    assert abs(fit.slope_hz_s - true_slope_hz_s) <= 100.0
    assert not fit.frequency_at_boundary
    assert not fit.slope_at_boundary


def test_window_groups_respect_actual_frame_span() -> None:
    tool = _tool()
    curve = np.ones(len(tool.RESIDUAL_GRID_HZ), dtype=float)

    def window(index: int, time_s: float):
        return tool.Window(
            association_index=index,
            branch_index=0,
            detection_time_s=time_s,
            probe_sample_start=index * 62_500,
            aligned_sample_start=index * 62_500,
            local_epoch_sample=0,
            initial_cfo_hz=0.0,
            glrt_exact_score=0.5,
            glrt_control_score=0.04,
            glrt_margin=0.46,
            selection_model_error_hz=0.0,
        )

    windows = tuple(window(index, index * 0.025) for index in range(4))
    likelihoods = {}
    for item in windows:
        likelihoods[item.analysis_key] = tuple(
            tool.FrameLikelihood(
                time_s=item.detection_time_s + offset,
                nco_cfo_hz=0.0,
                even_exact_power=curve,
                even_exact_ceiling=1.0,
                even_control_power=curve,
                even_control_ceiling=1.0,
                odd_exact_power=curve,
                odd_exact_ceiling=1.0,
                odd_control_power=curve,
                odd_control_ceiling=1.0,
            )
            for offset in (0.001, 0.019)
        )

    groups = tool.build_window_groups(windows, likelihoods, scale_ms=50)

    assert groups
    assert all(len(group) == 2 for group in groups)
    for group in groups:
        frames = tuple(frame for item in group for frame in likelihoods[item.analysis_key])
        assert frames[-1].time_s - frames[0].time_s <= 0.050
