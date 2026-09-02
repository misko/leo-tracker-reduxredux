from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import numpy as np
import pytest

from leo.analysis.standard.full_capture_glrt20ms import fractional_log_peak_offset


def _tool() -> ModuleType:
    path = Path(__file__).parents[2] / "tools" / "prototype_7fea_glrt_fractional_epoch.py"
    spec = importlib.util.spec_from_file_location("prototype_7fea_glrt_fractional_epoch", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_parabolic_peak_recovers_fractional_vertex() -> None:
    tool = _tool()
    offsets = np.arange(-2.0, 3.0)
    scores = 10.0 - (offsets - 0.23) ** 2

    assert tool.parabolic_peak(scores, offsets) == pytest.approx(0.23)


def test_log_parabolic_peak_recovers_log_score_vertex() -> None:
    tool = _tool()
    offsets = np.arange(-2.0, 3.0)
    scores = np.exp(2.0 - 1.7 * (offsets + 0.31) ** 2)

    assert tool.parabolic_peak(scores, offsets, logarithmic=True) == pytest.approx(-0.31)


def test_parabolic_peak_keeps_unbracketed_grid_winner() -> None:
    tool = _tool()
    offsets = np.arange(-2.0, 3.0)

    assert tool.parabolic_peak(np.arange(5.0), offsets) == 2.0


def test_quadratic_timing_fit_recovers_rate_and_residuals() -> None:
    tool = _tool()
    times = np.linspace(10.0, 20.0, 101)
    local = times - np.mean(times)
    curvature = -3.0e-7
    phases = 1.0e-3 + 4.0e-7 * local + 0.5 * curvature * local**2

    fit = tool.quadratic_timing_fit(times, phases, rf_reference_hz=10.0e9)

    assert fit["timing_curvature_s_s2"] == pytest.approx(curvature)
    assert fit["equivalent_doppler_rate_hz_s"] == pytest.approx(3_000.0)
    assert fit["residual_rms_us"] < 1e-9


def test_production_fractional_estimator_reproduces_all_7fea_replayed_peaks() -> None:
    path = (
        Path(__file__).parents[2]
        / "reports"
        / "figures"
        / "2026_09_02_7fea_glrt_fractional_epoch"
        / "fractional-glrt-epoch-prototype.json"
    )
    evidence = json.loads(path.read_text(encoding="utf-8"))
    rows = evidence["rows"]

    production = tuple(fractional_log_peak_offset(row["exact_scores"]) for row in rows)

    assert len(rows) == 652
    assert all(item is not None for item in production)
    assert (
        max(
            abs(float(actual) - row["log_peak_correction_samples"])
            for actual, row in zip(production, rows, strict=True)
        )
        < 1e-12
    )
