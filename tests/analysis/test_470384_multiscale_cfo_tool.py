from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest


def _tool() -> ModuleType:
    path = Path(__file__).parents[2] / "tools" / "report_470384_multiscale_cfo.py"
    spec = importlib.util.spec_from_file_location("report_470384_multiscale_cfo_tool", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _frames(count: int, *, start_s: float = 0.0, rate_hz_s: float = -3_800.0):
    return tuple(
        SimpleNamespace(
            frame_index=index,
            time_s=start_s + index / 750,
            measurement_supported=True,
            phase_update_applied=True,
            frequency_update_applied=True,
            absolute_cfo_measurement_hz=10_000 + rate_hz_s * (start_s + index / 750),
            tracked_absolute_cfo_hz=10_000 + rate_hz_s * (start_s + index / 750),
            tracked_doppler_rate_hz_s=rate_hz_s,
            frequency_sigma_hz=15.0,
            exact_coherence=0.12,
            control_coherence=0.01,
            coherence_margin=0.11,
        )
        for index in range(count)
    )


def _interval(tool: ModuleType, start_time_s: float, frames) -> object:
    return tool.TrackingInterval(
        source=SimpleNamespace(index=0),
        start_time_s=start_time_s,
        end_time_s=start_time_s + 0.070,
        result=SimpleNamespace(
            frames=tuple(frames),
            supported_frame_count=sum(item.measurement_supported for item in frames),
            phase_update_count=sum(item.phase_update_applied for item in frames),
            frequency_update_count=sum(item.frequency_update_applied for item in frames),
        ),
    )


def test_cubic_trajectory_frequency_and_derivative() -> None:
    tool = _tool()
    trajectory = tool.FrozenTrajectory((2.0, 3.0, 4.0, 5.0), 10.0, "branch", "track")

    assert trajectory.frequency_hz(12.0) == pytest.approx(41.0)
    assert trajectory.doppler_rate_hz_s(12.0) == pytest.approx(40.0)


def test_selection_reproduces_stride_after_quality_gates() -> None:
    tool = _tool()
    trajectory = tool.FrozenTrajectory((0.0, 1_000.0), 0.0, "branch", "track")
    detections = []
    for index in range(10):
        detections.append(
            {
                "time_s": index * 0.1,
                "sample_start": index * 100,
                "candidates": [
                    {
                        "rank": 1,
                        "local_epoch_sample": 7,
                        "scores": [
                            {
                                "method": "glrt64",
                                "margin": 0.2,
                                "tracking_cfo_hz": 1_000.0 + index,
                            }
                        ],
                    }
                ],
            }
        )

    selected = tool.select_source_windows(
        {"detections": detections},
        trajectory,
        start_s=0.0,
        end_s=1.0,
        minimum_margin=0.05,
        maximum_model_error_hz=20.0,
        accepted_stride=3,
    )

    assert [item.accepted_index for item in selected] == [0, 3, 6, 9]
    assert [item.index for item in selected] == [0, 1, 2, 3]


def test_rolling_frequency_fit_recovers_frame_cadence_line() -> None:
    tool = _tool()
    interval = _interval(tool, 5.0, _frames(53, rate_hz_s=-3_800.0))

    estimates = tool.rolling_frequency_estimates(interval, 0.050)

    assert estimates
    assert estimates[-1].doppler_rate_hz_s == pytest.approx(-3_800.0, abs=1e-6)
    assert estimates[-1].fit_rms_hz == pytest.approx(0.0, abs=1e-8)
    assert estimates[-1].time_s == pytest.approx(5.0 + 52 / 750)


def test_rolling_frequency_fit_does_not_bridge_rejected_frame_gap() -> None:
    tool = _tool()
    frames = list(_frames(60))
    for index in range(24, 29):
        frames[index].measurement_supported = False
    interval = _interval(tool, 0.0, frames)

    estimates = tool.rolling_frequency_estimates(interval, 0.020)

    assert estimates
    assert not any(29 / 750 <= item.time_s < 39 / 750 for item in estimates)


def test_zoom_selection_prefers_supported_frames_then_phase_updates() -> None:
    tool = _tool()
    first = list(_frames(20))
    second = list(_frames(20))
    third = list(_frames(20))
    for frame in first[:5]:
        frame.measurement_supported = False
    intervals = (
        _interval(tool, 0.1, first),
        _interval(tool, 0.8, second),
        _interval(tool, 0.9, third),
    )

    start_s, end_s = tool.select_strongest_zoom(
        intervals,
        start_s=0.0,
        end_s=1.5,
        duration_s=0.5,
    )

    assert start_s <= 0.8
    assert end_s >= 0.9 + 19 / 750


def test_multiscale_figure_renders(tmp_path: Path) -> None:
    tool = _tool()
    interval = _interval(tool, 4.0, _frames(53))
    trajectory = tool.FrozenTrajectory((-3_800.0, 10_000.0), 4.0, "branch", "track")
    destination = tmp_path / "multiscale.png"

    tool.render_multiscale_cfo(
        destination,
        (interval,),
        trajectory,
        x_limits_s=(4.0, 4.1),
        title="Test multiscale figure",
    )

    assert destination.is_file()
    assert destination.stat().st_size > 0


def _dense_document(tool: ModuleType) -> dict:
    frames = [
        {
            "reference_time_s": 33.7 + index / 750,
            "absolute_cfo_measurement_hz": 10_000.0 - 3_800.0 * index / 750,
            "model_cfo_hz": 10_000.0 - 7_000.0 * index / 750,
            "frequency_update_applied": index % 3 != 0,
            "phase_update_applied": index % 4 == 0,
            "phase_reset_detected": index % 7 == 0,
        }
        for index in range(30)
    ]
    return {
        "input": {
            "session_id": tool.SESSION_ID,
            "stream_id": "stream-0",
            "receiver_id": 0,
            "edge": "upper",
            "trajectory_id": tool.TRAJECTORY_ID,
        },
        "dense_tracking": {
            "source_window_count": 2,
            "returned_frame_count": len(frames),
            "frames": frames,
        },
    }


def test_dense_frame_document_binding_and_summary() -> None:
    tool = _tool()
    frames = tool.dense_frames_from_document(_dense_document(tool))

    summary = tool._dense_frame_summary(frames, limits_s=(33.7, 33.72))

    assert summary == {
        "frame_count": 15,
        "frequency_update_count": 10,
        "phase_update_count": 4,
        "phase_reset_count": 3,
    }


def test_all_frame_cfo_figure_renders_every_dense_row(tmp_path: Path) -> None:
    tool = _tool()
    frames = tool.dense_frames_from_document(_dense_document(tool))
    destination = tmp_path / "all-frame-cfo.png"

    tool.render_all_frame_cfo(
        destination,
        frames,
        full_limits_s=(33.7, 33.74),
        zoom_limits_s=(33.7, 33.72),
        source_window_count=2,
    )

    assert destination.is_file()
    assert destination.stat().st_size > 0
