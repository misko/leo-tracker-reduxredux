from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


def _tool():
    path = Path(__file__).parents[2] / "tools" / "analyze_edge_pilot_qam_timeline.py"
    spec = importlib.util.spec_from_file_location("edge_pilot_qam_timeline_tool", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_schedule_takes_first_20ms_of_every_50ms_inside_each_second() -> None:
    starts = _tool()._window_starts(
        2_000,
        outer_chunk_samples=1_000,
        subwindow_samples=50,
        probe_samples=20,
    )

    assert len(starts) == 40
    assert starts[:3] == ((0, 0, 0), (0, 1, 50), (0, 2, 100))
    assert starts[19] == (0, 19, 950)
    assert starts[20] == (1, 0, 1_000)
    assert starts[-1] == (1, 19, 1_950)


def test_schedule_rejects_ambiguous_window_geometry() -> None:
    tool = _tool()
    with pytest.raises(ValueError, match="probe must fit"):
        tool._window_starts(
            1_000,
            outer_chunk_samples=1_000,
            subwindow_samples=20,
            probe_samples=21,
        )
    with pytest.raises(ValueError, match="integral number"):
        tool._window_starts(
            1_000,
            outer_chunk_samples=1_000,
            subwindow_samples=60,
            probe_samples=20,
        )


def test_exploratory_positive_requires_both_qam_and_pilot_gates() -> None:
    tool = _tool()
    values = dict(
        index=0,
        outer_chunk_index=0,
        subwindow_index=0,
        sample_start=0,
        time_s=0.0,
        acquisition_status="complete",
        candidate_epoch_sample=37,
        baseband_cfo_hz=200_000.0,
        verify_score=0.8,
        control_score=0.1,
        pilot_margin=0.7,
        qam_status="complete",
        qam_accuracy=0.9,
        qam_rms_evm=0.2,
        frame_count=14,
    )

    assert tool.ProbeMetric(**values).exploratory_positive is True
    assert tool.ProbeMetric(**{**values, "pilot_margin": 0.049}).exploratory_positive is False
    assert tool.ProbeMetric(**{**values, "qam_accuracy": 0.599}).exploratory_positive is False


def test_one_outer_chunk_keeps_twenty_probe_indexes_and_coordinates_together() -> None:
    tool = _tool()
    rate = 2_500_000
    outer = tool.np.zeros(rate, dtype=tool.np.complex128)
    calibration = tool._calibration(0)
    wide = tool.SymbolwiseAcquisitionConfig(maximum_probe_samples=50_000)
    local = tool.SymbolwiseAcquisitionConfig(
        residual_cfo_min_hz=-20_000,
        residual_cfo_max_hz=20_000,
        coarse_cfo_step_hz=10_000,
        fine_cfo_radius_hz=20_000,
        retained_candidate_count=2,
        maximum_probe_samples=50_000,
    )

    metrics = tool._analyze_outer_chunk(
        (
            3,
            3 * rate,
            60,
            outer,
            rate,
            rate,
            125_000,
            50_000,
            calibration,
            wide,
            local,
            tool.StarlinkEdge.UPPER,
        )
    )

    assert len(metrics) == 20
    assert metrics[0].index == 60
    assert metrics[-1].index == 79
    assert metrics[0].time_s == 3.0
    assert metrics[-1].time_s == 3.95
