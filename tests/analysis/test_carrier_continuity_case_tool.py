from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest


def _tool():
    path = Path(__file__).parents[2] / "tools" / "report_carrier_continuity_case.py"
    spec = importlib.util.spec_from_file_location("carrier_continuity_case_tool", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_boundary_phase_integrates_only_straight_frequency_segments() -> None:
    tool = _tool()
    boundary = tool.BOUNDARIES[0]
    epsilon = 1e-6
    for time_s, segment in (
        (boundary.time_s - 0.25, boundary.pre),
        (boundary.time_s + 0.25, boundary.post),
    ):
        leading = boundary.nominal_phase_cycles(time_s + epsilon)
        trailing = boundary.nominal_phase_cycles(time_s - epsilon)
        numerical_frequency = float((leading - trailing) / (2.0 * epsilon))
        assert numerical_frequency == pytest.approx(float(segment.frequency_hz(time_s)), rel=1e-6)
    assert float(boundary.nominal_phase_cycles(boundary.time_s)) == 0.0


def _frames(tool, boundary, *, jump_cycles: float):
    times = np.concatenate(
        (
            np.linspace(boundary.time_s - 0.8, boundary.time_s - 0.03, 80),
            np.linspace(boundary.time_s + 0.03, boundary.time_s + 0.8, 80),
        )
    )
    residual = 0.17 + 3.0 * (times - boundary.time_s)
    residual[times >= boundary.time_s] += jump_cycles
    phases = tool._wrap_cycles(boundary.nominal_phase_cycles(times) + residual)
    return tuple(
        tool.FrameObservation(
            index // 4,
            "pre" if time_s < boundary.time_s else "post",
            float(time_s),
            float(phase),
            0.4,
            0.05,
        )
        for index, (time_s, phase) in enumerate(zip(times, phases, strict=True))
    )


def test_phase_metric_distinguishes_continuous_and_reset_carriers() -> None:
    tool = _tool()
    boundary = tool.BOUNDARIES[0]
    continuous, _ = tool._phase_metrics(boundary, _frames(tool, boundary, jump_cycles=0.0))
    reset, _ = tool._phase_metrics(boundary, _frames(tool, boundary, jump_cycles=0.25))
    assert abs(continuous["wrapped_phase_jump_cycles"]) < 1e-4
    assert abs(abs(reset["wrapped_phase_jump_cycles"]) - 0.25) < 1e-4
    assert continuous["continuous_to_reset_error_ratio"] < 1.1
    assert reset["continuous_to_reset_error_ratio"] > 5.0


def test_candidate_selection_occurs_after_independent_scoring() -> None:
    tool = _tool()
    boundary = tool.BOUNDARIES[0]
    time_s = boundary.time_s - 0.2
    expected = float(boundary.pre.frequency_hz(time_s))
    candidates = (
        tool.Candidate(100, time_s, 0, 4, 25_000.0, expected + 20_000.0, 0.8, 0.1, 0.7),
        tool.Candidate(100, time_s, 1, 7, expected + 100.0, expected + 100.0, 0.4, 0.1, 0.3),
    )
    selected = tool._select_line_candidates(boundary, candidates)
    assert selected == (candidates[1],)
