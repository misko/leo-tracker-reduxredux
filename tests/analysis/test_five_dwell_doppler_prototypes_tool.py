from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import numpy as np
import pytest


def _tool() -> ModuleType:
    tools_root = Path(__file__).parents[2] / "tools"
    path = tools_root / "report_five_dwell_doppler_prototypes.py"
    sys.path.insert(0, str(tools_root))
    try:
        spec = importlib.util.spec_from_file_location(
            "report_five_dwell_doppler_prototypes_tool", path
        )
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(tools_root))
    return module


def _window(tool: ModuleType, index: int, *, aligned_start: int) -> object:
    return tool.CandidateWindow(
        window_index=index,
        detection_time_s=10.0 + 0.025 * index,
        probe_sample_start=25_000_000 + 62_500 * index,
        aligned_sample_start=aligned_start,
        local_epoch_sample=0,
        initial_cfo_hz=0.0,
        analysis_cfo_hz=0.0,
        glrt_exact_score=0.2,
        glrt_control_score=0.02,
        glrt_margin=0.18,
        selection_model_error_hz=0.0,
    )


def _likelihood(tool: ModuleType, *, time_s: float, cfo_hz: float):
    grid = tool.semicoherent.RESIDUAL_GRID_HZ
    exact = np.exp(-0.5 * ((grid - cfo_hz) / 25.0) ** 2)
    control = 0.1 * np.ones_like(exact)
    return tool.semicoherent.FrameLikelihood(
        time_s=time_s,
        nco_cfo_hz=0.0,
        even_exact_power=exact,
        even_exact_ceiling=1.0,
        even_control_power=control,
        even_control_ceiling=1.0,
        odd_exact_power=exact,
        odd_exact_ceiling=1.0,
        odd_control_power=control,
        odd_control_ceiling=1.0,
    )


def test_timing_break_uses_wrapped_frame_phase() -> None:
    tool = _tool()
    windows = (
        _window(tool, 0, aligned_start=10_000),
        _window(tool, 1, aligned_start=20_025),
        _window(tool, 2, aligned_start=30_025),
    )

    assert tool.timing_break_window_indices(windows, {0, 1, 2}) == (1,)


def test_state_intercepts_remove_reset_bias_from_common_rate() -> None:
    tool = _tool()
    frame_rows = []
    windows = []
    row_index = 0
    true_rate_hz_s = -3_800.0
    for window_index in range(9):
        state_index = window_index // 3
        state_center_s = 10.025 + 0.075 * state_index
        state_intercept_hz = 2_000.0 * state_index
        window_start_s = 10.0 + 0.025 * window_index
        windows.append(
            _window(tool, window_index, aligned_start=10_000 + 62_500 * window_index)
        )
        for frame_index in range(15):
            time_s = window_start_s + frame_index / 750.0
            cfo_hz = state_intercept_hz + true_rate_hz_s * (
                time_s - state_center_s
            )
            frame_rows.append(
                tool.FrameEvidence(
                    row_index=row_index,
                    window_index=window_index,
                    time_s=time_s,
                    train_cfo_hz=cfo_hz,
                    validation_cfo_hz=cfo_hz,
                    nco_cfo_hz=0.0,
                    train_exact_score=0.5,
                    train_control_score=0.05,
                    train_margin=0.45,
                    likelihood=_likelihood(tool, time_s=time_s, cfo_hz=cfo_hz),
                )
            )
            row_index += 1
    spec = tool.DwellSpec(
        label="D1 · synthetic",
        session_id="synthetic",
        run_id="run",
        stream_id="stream-0",
        receiver_id=0,
        edge=tool.StarlinkEdge.LOWER,
        analysis_root=Path("."),
        branch_id="branch",
        branch_start_s=10.0,
        branch_end_s=10.22,
        branch_reference_time_s=10.1,
        branch_coefficients_hz=(0.0, 0.0),
        anchor_time_s=10.1,
    )

    predictions, details = tool.fit_model_predictions(
        spec, tuple(frame_rows), tuple(windows)
    )

    assert details["coherent_segment_count"] == 3
    assert predictions["M0"].rate_at_reference_hz_s > 10_000.0
    assert predictions["M1"].rate_at_reference_hz_s == pytest.approx(
        true_rate_hz_s, abs=1e-6
    )
    assert predictions["M2"].rate_progression_hz_s2 == pytest.approx(0.0, abs=1e-5)


def test_validation_samples_held_out_frequency_likelihood() -> None:
    tool = _tool()
    likelihood = _likelihood(tool, time_s=12.0, cfo_hz=100.0)
    frame = tool.FrameEvidence(
        row_index=0,
        window_index=0,
        time_s=12.0,
        train_cfo_hz=100.0,
        validation_cfo_hz=100.0,
        nco_cfo_hz=0.0,
        train_exact_score=1.0,
        train_control_score=0.1,
        train_margin=0.9,
        likelihood=likelihood,
    )
    prediction = tool.ModelPrediction(
        model="M0",
        frame_indices=(0,),
        predicted_cfo_hz=(100.0,),
        rate_at_reference_hz_s=-3_800.0,
        rate_reference_time_s=12.0,
        rate_progression_hz_s2=None,
        segment_count=1,
    )

    result = tool.validate_prediction(prediction, (frame,))

    assert result["validation_cfo_rms_hz"] == pytest.approx(0.0)
    assert result["validation_qin_beats_control_fraction"] == pytest.approx(1.0)
    assert result["validation_margin_mean"] == pytest.approx(0.9)


def test_paired_probe_figure_renders_unavailable_models(tmp_path: Path) -> None:
    tool = _tool()
    validation = {
        "frame_count": 30,
        "validation_cfo_rms_hz": 20.0,
        "per_probe": [
            {"window_index": 0, "validation_cfo_rms_hz": 18.0},
            {"window_index": 1, "validation_cfo_rms_hz": 22.0},
        ],
    }
    result = {
        "spec": {"session_id": "cap-20260821T000000-synthetic"},
        "paired_to_matched_global": {
            "M1": {
                "matched_global": {
                    "frame_count": 30,
                    "validation_cfo_rms_hz": 40.0,
                    "per_probe": [
                        {"window_index": 0, "validation_cfo_rms_hz": 36.0},
                        {"window_index": 1, "validation_cfo_rms_hz": 44.0},
                    ],
                },
                "state_model": validation,
                "validation_cfo_rms_reduction_fraction": 0.5,
            }
        },
    }
    destination = tmp_path / "paired.png"

    tool.render_paired_probe_validation([result], destination)

    assert destination.is_file()
    assert destination.stat().st_size > 0
