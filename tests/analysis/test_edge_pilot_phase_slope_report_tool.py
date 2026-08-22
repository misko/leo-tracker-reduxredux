from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np

from leo.analysis.qam import PilotPhaseSlopeFrame
from leo.analysis.starlink import OFDM_SYMBOL_DURATION_S


def _tool():
    path = Path(__file__).parents[2] / "tools" / "report_edge_pilot_phase_slope_figures.py"
    spec = importlib.util.spec_from_file_location("edge_pilot_phase_slope_report_tool", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _candidate(cfo_hz: float, margin: float, *, rank: int, epoch: int = 10) -> dict:
    return {
        "rank": rank,
        "local_epoch_sample": epoch,
        "acquired_cfo_hz": cfo_hz - 100.0,
        "scores": [
            {
                "method": "glrt64",
                "tracking_cfo_hz": cfo_hz,
                "margin": margin,
            }
        ],
    }


def test_selection_applies_margin_and_model_gates_before_stride() -> None:
    tool = _tool()
    trajectory = tool.FrozenTrajectory((1_000.0,), 0.0, "branch", "trajectory")
    scan = {
        "detections": [
            {
                "time_s": float(index),
                "sample_start": index * 100,
                "candidates": [
                    _candidate(1_050.0, 0.2, rank=0, epoch=index + 1),
                    _candidate(1_005.0, 0.1, rank=1, epoch=index + 2),
                ],
            }
            for index in range(6)
        ]
    }
    scan["detections"][1]["candidates"] = [_candidate(1_000.0, 0.01, rank=0)]
    scan["detections"][3]["candidates"] = [_candidate(4_000.0, 0.2, rank=0)]

    selected = tool._select_windows(
        scan,
        trajectory,
        start_s=0.0,
        end_s=5.0,
        minimum_margin=0.05,
        maximum_model_error_hz=100.0,
        accepted_stride=2,
    )

    assert [item.detection_time_s for item in selected] == [0.0, 4.0]
    assert all(item.candidate_rank == 1 for item in selected)
    assert selected[0].aligned_sample_start == 2
    assert selected[1].aligned_sample_start == 406


def test_phase_display_recovers_known_slope_without_connecting_frames() -> None:
    tool = _tool()
    expected = np.ones((300, 8), dtype=np.complex128)
    times_s = (np.arange(300, dtype=float) + 2.5) * OFDM_SYMBOL_DURATION_S
    times_s -= np.mean(times_s)
    frequency_hz = 425.0
    phases = (-2.1, 1.7)
    channel = np.exp(1j * np.linspace(-1.2, 1.1, 8))
    pilots = np.asarray(
        [
            expected
            * channel[None, :]
            * np.exp(1j * (phase + 2 * np.pi * frequency_hz * times_s))[:, None]
            for phase in phases
        ]
    )
    frames = tuple(
        PilotPhaseSlopeFrame(
            frame_index=index,
            frame_start_sample=index * 3_333,
            reference_sample=1_661.0,
            residual_cfo_hz=frequency_hz,
            absolute_cfo_hz=100_000.0 + frequency_hz,
            frequency_uncertainty_hz=1.0,
            phase_at_reference_rad=phase,
            exact_coherence=1.0,
            control_coherence=0.0,
            coherence_margin=1.0,
            phase_residual_rms_rad=0.0,
        )
        for index, phase in enumerate(phases)
    )

    display, residual = tool._phase_arrays(pilots, expected, frames)

    np.testing.assert_allclose(display[:, 150], phases, atol=0.01)
    np.testing.assert_allclose(residual, 0.0, atol=1e-10)
    slopes = np.polyfit(times_s, display.T, 1)[0] / (2 * np.pi)
    np.testing.assert_allclose(slopes, frequency_hz, atol=1e-9)
