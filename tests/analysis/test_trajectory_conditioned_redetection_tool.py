from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from leo.analysis.starlink.acquisition import NumericalStatus
from leo.analysis.starlink.pilot_methods import (
    PilotMethod,
    PilotMethodScore,
    PilotProbeDetection,
)


def _tool():
    path = Path(__file__).parents[2] / "tools" / "run_trajectory_conditioned_redetection.py"
    spec = importlib.util.spec_from_file_location("trajectory_redetection_tool", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_cli_requires_explicit_edge(monkeypatch: pytest.MonkeyPatch) -> None:
    tool = _tool()
    monkeypatch.setattr(sys, "argv", ["trajectory-redetection"])
    with pytest.raises(SystemExit) as error:
        tool._arguments()
    assert error.value.code == 2

    monkeypatch.setattr(sys, "argv", ["trajectory-redetection", "--edge", "upper"])
    assert tool._arguments().edge == "upper"


def test_observations_expand_every_complete_row_to_all_methods() -> None:
    tool = _tool()
    row = {
        "index": "0",
        "sample_start": "100",
        "time_s": "0.1",
        "acquired_cfo_hz": "300000",
        "anchor8_score": "0.8",
        "anchor8_control_score": "0.1",
        "anchor8_margin": "0.7",
        "differential16_score": "0.8",
        "differential16_control_score": "0.1",
        "differential16_margin": "0.7",
        "differential16_residual_cfo_hz": "10",
        "differential32_score": "0.8",
        "differential32_control_score": "0.1",
        "differential32_margin": "0.7",
        "differential32_residual_cfo_hz": "20",
        "glrt32_score": "0.8",
        "glrt32_control_score": "0.1",
        "glrt32_margin": "0.7",
        "glrt32_residual_cfo_hz": "30",
        "glrt64_score": "0.8",
        "glrt64_control_score": "0.1",
        "glrt64_margin": "0.7",
        "glrt64_residual_cfo_hz": "40",
        "edge_tracker_score": "0.8",
        "edge_tracker_control_score": "0.1",
        "edge_tracker_margin": "0.7",
        "symbolwise_margin": "0.7",
        "qam_accuracy": "0.9",
    }

    observations = tool._observations((row,))

    assert tuple(item.method for item in observations) == tuple(PilotMethod)
    assert (
        next(item for item in observations if item.method is PilotMethod.GLRT64).tracking_cfo_hz
        == 300_040
    )

    corrected = tool.CorrectedProbe(
        "family",
        "trajectory",
        0,
        PilotProbeDetection(
            NumericalStatus.COMPLETE,
            100,
            0.1,
            2,
            20.0,
            (
                PilotMethodScore(
                    PilotMethod.GLRT64,
                    0.9,
                    0.1,
                    0.8,
                    5.0,
                    25.0,
                ),
            ),
            None,
            None,
            "corrected",
        ),
    )

    records = tool._timeline_records((row,), (corrected,))

    assert records == (
        {
            "family_id": "family",
            "trajectory_id": "trajectory",
            "probe_index": 0,
            "sample_start": 100,
            "time_s": 0.1,
            "method": "glrt64",
            "baseline_tracking_cfo_hz": 300_040.0,
            "corrected_acquired_cfo_hz": 20.0,
            "corrected_tracking_cfo_hz": 25.0,
            "baseline_margin": 0.7,
            "corrected_exact_score": 0.9,
            "corrected_control_score": 0.1,
            "corrected_margin": 0.8,
            "margin_delta": 0.10000000000000009,
        },
    )
