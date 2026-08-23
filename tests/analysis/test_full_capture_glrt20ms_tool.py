from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
from PIL import Image


def _tool():
    path = Path(__file__).parents[2] / "tools" / "analyze_full_capture_glrt20ms.py"
    spec = importlib.util.spec_from_file_location("full_capture_glrt20ms_tool", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_huber_frame_line_resists_one_large_outlier() -> None:
    tool = _tool()
    times = np.linspace(0.0, 0.019, 15)
    values = 22_000.0 - 6_000.0 * times
    values[7] += 40_000.0

    fit = tool._fit_supported_frame_line(times, values)

    assert fit["available"] is True
    assert abs(float(fit["slope_hz_s"]) + 6_000.0) < 50.0
    assert fit["outlier_count"] == 1


def test_six_panel_plot_has_shared_full_time_axis(tmp_path: Path) -> None:
    tool = _tool()
    rows = tuple(
        tool.WindowResult(
            probe_index=index,
            sample_start=index * 25_000,
            start_time_s=index * 0.01,
            center_time_s=index * 0.01 + 0.01,
            end_time_s=index * 0.01 + 0.02,
            acquisition_status="complete",
            candidate_count=10,
            best_candidate_rank=0,
            epoch_sample=12,
            acquired_cfo_hz=20_000.0 - index * 60.0,
            residual_cfo_hz=10.0,
            tracking_cfo_hz=20_010.0 - index * 60.0,
            glrt_exact_score=0.2,
            glrt_control_score=0.05,
            glrt_margin=0.15 if index % 2 else 0.01,
            passed_margin_gate=bool(index % 2),
            lattice_frame_count=15,
            measured_frame_count=14,
            robust_line_available=True,
            robust_reference_time_s=index * 0.01 + 0.01,
            robust_cfo_at_reference_hz=20_000.0 - index * 60.0,
            robust_slope_hz_s=-6_000.0 + index,
            robust_slope_sigma_hz_s=100.0,
            robust_residual_rms_hz=20.0,
            robust_median_absolute_residual_hz=10.0,
            robust_mad_scale_hz=5.0,
            robust_outlier_count=1,
            robust_converged=True,
            reason="Huber degree-one frame-CFO line available",
        )
        for index in range(30)
    )
    path = tmp_path / "three-panel.png"

    tool._plot(
        rows,
        session_id="session",
        path_label="stream-0/RX0 upper",
        margin_gate=0.025,
        output_path=path,
    )

    with Image.open(path) as image:
        assert image.width >= 2_000
        assert image.height >= 1_500


def test_production_hough_dealias_recovers_one_aliased_linear_track() -> None:
    tool = _tool()
    alias_spacing_hz = 1.0 / 4.4e-6
    rows = []
    for index in range(201):
        start_s = index * 0.01
        raw_cfo_hz = 80_000.0 - 5_000.0 * start_s
        if start_s >= 1.0:
            raw_cfo_hz += alias_spacing_hz
        rows.append(
            tool.WindowResult(
                probe_index=index,
                sample_start=index * 25_000,
                start_time_s=start_s,
                center_time_s=start_s + 0.01,
                end_time_s=start_s + 0.02,
                acquisition_status="complete",
                candidate_count=10,
                best_candidate_rank=0,
                epoch_sample=12,
                acquired_cfo_hz=raw_cfo_hz,
                residual_cfo_hz=0.0,
                tracking_cfo_hz=raw_cfo_hz,
                glrt_exact_score=0.60,
                glrt_control_score=0.05,
                glrt_margin=0.55,
                passed_margin_gate=True,
                lattice_frame_count=15,
                measured_frame_count=15,
                robust_line_available=True,
                robust_reference_time_s=start_s + 0.01,
                robust_cfo_at_reference_hz=raw_cfo_hz,
                robust_slope_hz_s=-5_000.0,
                robust_slope_sigma_hz_s=1.0,
                robust_residual_rms_hz=10.0,
                robust_median_absolute_residual_hz=5.0,
                robust_mad_scale_hz=5.0,
                robust_outlier_count=0,
                robust_converged=True,
                reason="test",
            )
        )

    analysis = tool._hough_dealiased_tracks(tuple(rows))

    assert analysis["published_track_count"] == 1
    track = analysis["tracks"][0]
    assert track["observation_count"] >= 170
    assert abs(track["slope_hz_s"] + 5_000.0) < 1.0
    assert len(set(track["observed_alias_indices"])) >= 2


def test_robust_slope_trend_reports_rate_and_rate_change() -> None:
    tool = _tool()
    rows = tuple(
        tool.WindowResult(
            probe_index=index,
            sample_start=index * 25_000,
            start_time_s=index * 0.01,
            center_time_s=index * 0.01 + 0.01,
            end_time_s=index * 0.01 + 0.02,
            acquisition_status="complete",
            candidate_count=10,
            best_candidate_rank=0,
            epoch_sample=12,
            acquired_cfo_hz=20_000.0,
            residual_cfo_hz=0.0,
            tracking_cfo_hz=20_000.0,
            glrt_exact_score=0.20,
            glrt_control_score=0.05,
            glrt_margin=0.15,
            passed_margin_gate=True,
            lattice_frame_count=15,
            measured_frame_count=15,
            robust_line_available=True,
            robust_reference_time_s=index * 0.01 + 0.01,
            robust_cfo_at_reference_hz=20_000.0,
            robust_slope_hz_s=-4_000.0 + 20.0 * (index * 0.01 + 0.01),
            robust_slope_sigma_hz_s=1.0,
            robust_residual_rms_hz=10.0,
            robust_median_absolute_residual_hz=5.0,
            robust_mad_scale_hz=5.0,
            robust_outlier_count=0,
            robust_converged=True,
            reason="test",
        )
        for index in range(100)
    )

    trend = tool._robust_slope_trend(rows)

    assert trend is not None
    assert trend["point_count"] == 100
    assert abs(trend["doppler_rate_change_hz_s2"] - 20.0) < 1e-6


def test_summary_distinguishes_detection_from_line_availability() -> None:
    tool = _tool()
    base = dict(
        probe_index=0,
        sample_start=0,
        start_time_s=0.0,
        center_time_s=0.01,
        end_time_s=0.02,
        acquisition_status="complete",
        candidate_count=10,
        best_candidate_rank=0,
        epoch_sample=1,
        acquired_cfo_hz=0.0,
        residual_cfo_hz=0.0,
        tracking_cfo_hz=0.0,
        glrt_exact_score=0.2,
        glrt_control_score=0.1,
        glrt_margin=0.1,
        lattice_frame_count=15,
        measured_frame_count=15,
        robust_reference_time_s=0.01,
        robust_cfo_at_reference_hz=0.0,
        robust_slope_hz_s=-6_000.0,
        robust_slope_sigma_hz_s=10.0,
        robust_residual_rms_hz=1.0,
        robust_median_absolute_residual_hz=1.0,
        robust_mad_scale_hz=5.0,
        robust_outlier_count=0,
        robust_converged=True,
        reason="test",
    )
    rows = (
        tool.WindowResult(**base, passed_margin_gate=True, robust_line_available=True),
        tool.WindowResult(
            **{**base, "probe_index": 1, "center_time_s": 0.02},
            passed_margin_gate=False,
            robust_line_available=True,
        ),
    )

    summary = tool._summary(rows)

    assert summary["margin_pass_count"] == 1
    assert summary["robust_line_count"] == 2
    assert summary["margin_pass_with_robust_line_count"] == 1
