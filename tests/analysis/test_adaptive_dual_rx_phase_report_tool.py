from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import numpy as np
import pytest


def _tool() -> ModuleType:
    path = Path(__file__).parents[2] / "tools" / "report_adaptive_dual_rx_phase.py"
    spec = importlib.util.spec_from_file_location("adaptive_dual_rx_phase_tool", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _hypothesis(
    visit: int,
    time_s: float,
    frequencies_hz: tuple[float, float],
    phase_deg: float,
) -> dict:
    return {
        "visit_index": visit,
        "target_index": 0,
        "acquisition_time_s": time_s,
        "signal_frequencies_hz": list(frequencies_hz),
        "signal_separation_hz": abs(frequencies_hz[1] - frequencies_hz[0]),
        "double_difference_deg": phase_deg,
        "double_relative_frequency_hz": 0.1,
        "quality_floor": 0.9,
    }


def test_association_connects_signal_order_reversal_at_alias_boundary() -> None:
    tool = _tool()
    alias_hz = tool.SYMBOL_ALIAS_HZ
    document = {
        "hypotheses": [
            _hypothesis(index, float(index), (-112_000 + index * 500, -82_000 + index * 500), 0)
            for index in range(3)
        ]
        + [
            _hypothesis(
                3,
                3.0,
                (-80_500, -110_500 + alias_hz),
                0,
            )
        ]
    }
    document["hypotheses"][-1]["signal_separation_hz"] = 30_000

    paths = tool.associate(document)

    assert len(paths) == 1
    assert len(paths[0]) == 4
    orientations = [state.orientation for state in paths[0]]
    assert orientations[:3] == [orientations[0]] * 3
    assert orientations[3] != orientations[0]


def test_association_is_unchanged_when_phase_is_randomized() -> None:
    tool = _tool()
    hypotheses = [
        _hypothesis(index, float(index), (-50_000 - 500 * index, -20_000 - 400 * index), 0)
        for index in range(6)
    ]
    original = {"hypotheses": hypotheses}
    randomized = {
        "hypotheses": [
            {**row, "double_difference_deg": phase}
            for row, phase in zip(hypotheses, (170, -80, 25, 100, -160, 45), strict=True)
        ]
    }

    original_path = tool.associate(original)[0]
    randomized_path = tool.associate(randomized)[0]

    def identity(path):
        return [(state.hypothesis_id, state.orientation) for state in path]

    assert identity(original_path) == identity(randomized_path)


def test_phase_metrics_recover_a_linear_track_after_association() -> None:
    tool = _tool()
    states = [
        tool.AssociationState(
            hypothesis_id=index,
            orientation=0,
            visit_index=index,
            target_index=0,
            time_s=float(index),
            frequencies_hz=(-50_000 - index, -20_000 - index),
            separation_hz=30_000,
            phase_deg=20 + 24 * index,
            phase_rate_hz=24 / 360,
            quality=0.9,
        )
        for index in range(7)
    ]

    metrics = tool.phase_metrics(states, np.random.default_rng(7))

    assert metrics["linear_slope_deg_s"] == pytest.approx(24.0)
    assert metrics["linear_residual_rms_deg"] == pytest.approx(0.0, abs=1e-10)
    assert metrics["increment_concentration"] == pytest.approx(1.0)
    assert metrics["median_abs_rate_prediction_error_deg"] == pytest.approx(
        0.0, abs=1e-10
    )
