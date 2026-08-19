from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest


def _load_tool():
    path = Path(__file__).parents[2] / "tools" / "render_four_path_glrt64_feedback.py"
    spec = importlib.util.spec_from_file_location("four_path_glrt64_feedback_tool", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_recorded_clock_alignment_preserves_radio_start_skew() -> None:
    tool = _load_tool()
    origin = 1_787_121_029_924_226_035
    later = 1_787_121_029_925_651_245

    assert tool.aligned_time_s(0.0, origin, origin) == 0.0
    assert tool.aligned_time_s(0.0, later, origin) == pytest.approx(0.001425210)
    assert tool.aligned_time_s(6.2, later, origin) == pytest.approx(6.201425210)


def test_persisted_polynomial_uses_reference_time_and_high_power_first() -> None:
    tool = _load_tool()
    fit = {"coefficients_hz": [2.0, 3.0, 5.0], "reference_time_s": 10.0}

    values = tool.evaluate_trajectory_hz(fit, np.asarray([10.0, 12.0]))

    assert values.tolist() == pytest.approx([5.0, 19.0])
