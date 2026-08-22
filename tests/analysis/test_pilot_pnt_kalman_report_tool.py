from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path
from types import ModuleType


def _tool() -> ModuleType:
    path = Path(__file__).parents[2] / "tools" / "report_pilot_pnt_kalman.py"
    spec = importlib.util.spec_from_file_location("pilot_pnt_kalman_report_tool", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_standard_rate_uses_only_degree_one_tracks_and_nearest_frequency() -> None:
    tool = _tool()
    bank = {
        "trajectories": [
            {
                "absolute_coefficients_hz": [-3_000.0, 90_000.0],
                "reference_time_s": 1.0,
                "start_s": 0.0,
                "end_s": 2.0,
            },
            {
                "absolute_coefficients_hz": [8.0, -4_000.0, 100_000.0],
                "reference_time_s": 1.0,
                "start_s": 0.0,
                "end_s": 2.0,
            },
            {
                "absolute_coefficients_hz": [-6_000.0, 110_000.0],
                "reference_time_s": 1.0,
                "start_s": 0.0,
                "end_s": 2.0,
            },
        ]
    }

    assert tool._standard_rate(bank, time_s=1.0, cfo_hz=109_900.0) == -6_000.0
    assert tool._standard_rate(bank, time_s=3.0, cfo_hz=109_900.0) is None


def test_rms_fails_closed_for_no_accepted_phase_updates() -> None:
    tool = _tool()

    assert math.isnan(tool._rms([]))
    assert tool._rms([3.0, 4.0]) == math.sqrt(12.5)
