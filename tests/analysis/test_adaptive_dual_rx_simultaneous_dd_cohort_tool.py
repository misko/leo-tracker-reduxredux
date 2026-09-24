from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pytest


def _module() -> Any:
    path = Path("tools/report_adaptive_dual_rx_simultaneous_dd_cohort.py")
    spec = importlib.util.spec_from_file_location("_simultaneous_dd_cohort", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_circular_profile_recovers_wrapped_full_circle_rate() -> None:
    module = _module()
    times = np.asarray((0.0, 0.7, 1.8, 3.2, 4.9, 6.1))
    slope = 23.0
    phases = np.degrees(np.angle(np.exp(1j * np.radians(170.0 + slope * times))))
    result = module.circular_profile(times, phases, np.full(len(times), 5.0))
    assert result["best_slope_deg_s"] == pytest.approx(slope, abs=module.SLOPE_STEP_DEG_S)
    assert result["best_profile_resultant"] == pytest.approx(1.0)
    assert result["competing_local_maxima"]


def test_association_audit_uses_corrected_rf_and_exact_times_without_phase() -> None:
    module = _module()
    rows = {
        10: {
            "centers_hz": [100_000.0, 134_000.0],
            "source_separation_hz": 34_000.0,
            "receiver_offset_hz": -676_500.0,
            "exact_time_s": 1.0,
        },
        14: {
            "centers_hz": [99_000.0, 133_100.0],
            "source_separation_hz": 34_100.0,
            "receiver_offset_hz": -676_450.0,
            "exact_time_s": 1.6,
        },
    }
    result = module._association_audit(rows, [10, 14])
    assert result["phase_used"] is False
    assert result["all_transitions_pass_corrected_rf_and_time_gates"] is True


def test_regular_cadence_exposes_full_cycle_slope_alias() -> None:
    module = _module()
    times = np.arange(8, dtype=float)
    phases = np.degrees(np.angle(np.exp(1j * np.radians(23.0 * times))))
    result = module.circular_profile(times, phases, np.full(len(times), 5.0))
    maxima = result["competing_local_maxima"]
    exact = [row for row in maxima if row["profile_resultant"] == pytest.approx(1.0)]
    assert len(exact) >= 2
    slopes = sorted(row["slope_deg_s"] for row in exact)
    assert any(
        right - left == pytest.approx(360.0)
        for left, right in zip(slopes, slopes[1:], strict=False)
    )
