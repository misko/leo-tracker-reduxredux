from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest


def _tool():
    path = Path(__file__).parents[2] / "tools" / "report_shifted_pilot_grid_experiment.py"
    spec = importlib.util.spec_from_file_location("shifted_pilot_grid_experiment_tool", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _frames(tool, times: np.ndarray, frequencies: np.ndarray, sigma_hz: float = 2.0):
    return tuple(
        tool.FrameMeasurement(
            source_index=0,
            frame_start_sample=index,
            reference_time_s=float(time_s),
            absolute_cfo_hz=float(cfo_hz),
            frequency_uncertainty_hz=sigma_hz,
            exact_coherence=0.8,
            control_coherence=0.1,
            coherence_margin=0.7,
        )
        for index, (time_s, cfo_hz) in enumerate(zip(times, frequencies, strict=True))
    )


def test_shifted_epoch_preserves_absolute_frame_lattice() -> None:
    tool = _tool()
    source = tool.SourceWindow(0, 1.0, 2_500_000, 1_250, 10_000.0, 0.5, 0)

    base_epoch = tool._epoch_for_shifted_start(source, 2_500_000, 2_500_000.0)
    shifted_start = 2_512_500
    shifted_epoch = tool._epoch_for_shifted_start(source, shifted_start, 2_500_000.0)
    base_starts = {
        source.probe_sample_start + round(base_epoch + index * 2_500_000 / 750)
        for index in range(20)
    }
    shifted_starts = {
        shifted_start + round(shifted_epoch + index * 2_500_000 / 750)
        for index in range(20)
    }

    assert len(base_starts & shifted_starts) >= 10


def test_step_model_prefers_a_fixed_frequency_step() -> None:
    tool = _tool()
    times = np.arange(60, dtype=float) / 750
    frequencies = 8_000.0 - 3_500.0 * times + np.where(times >= times[30], -180.0, 0.0)

    result = tool._best_step_model(
        _frames(tool, times, frequencies), nominal_boundary_time_s=float(times[30])
    )

    assert result.scanned_delta_bic > 100
    assert result.scanned_step_time_s == pytest.approx((times[29] + times[30]) / 2)
    assert result.scanned_step_hz == pytest.approx(-180.0)
    assert result.fixed_step_hz == pytest.approx(-180.0)


def test_step_model_penalizes_a_smooth_line() -> None:
    tool = _tool()
    times = np.arange(60, dtype=float) / 750
    frequencies = 8_000.0 - 3_500.0 * times

    result = tool._best_step_model(
        _frames(tool, times, frequencies), nominal_boundary_time_s=float(times[30])
    )

    assert result.scanned_delta_bic < 0
    assert abs(result.fixed_step_hz) < 1e-8


def test_pair_step_is_evaluated_at_a_common_epoch() -> None:
    tool = _tool()
    left = tool.WindowFit(
        0,
        0.0,
        1.0,
        1.01,
        15,
        15,
        1.0,
        1 / 750,
        0.5,
        0.4,
        1_000.0,
        900.0,
        100.0,
        -4_000.0,
        100.0,
        10.0,
        12.0,
        True,
        (),
    )
    right = tool.WindowFit(
        1,
        0.0,
        1.025,
        1.035,
        15,
        15,
        1.0,
        1 / 750,
        0.5,
        0.4,
        720.0,
        620.0,
        100.0,
        -4_000.0,
        100.0,
        10.0,
        12.0,
        True,
        (),
    )

    result = tool._pair_steps((left, right,))

    assert len(result) == 1
    assert result[0].inferred_step_hz == pytest.approx(-180.0)


def test_same_absolute_frames_are_compared_within_source() -> None:
    tool = _tool()
    frame = tool.FrameMeasurement(0, 100, 1.0, 2_000.0, 10.0, 0.8, 0.1, 0.7)
    shifted = tool.FrameMeasurement(0, 100, 1.0, 2_003.0, 10.0, 0.8, 0.1, 0.7)
    unrelated = tool.FrameMeasurement(1, 100, 1.0, 9_000.0, 10.0, 0.8, 0.1, 0.7)

    result = tool._same_frame_summary((frame, unrelated), (shifted,))

    assert result == {
        "matched_frame_count": 1,
        "cfo_difference_rms_hz": pytest.approx(3.0),
        "cfo_difference_max_absolute_hz": pytest.approx(3.0),
    }
