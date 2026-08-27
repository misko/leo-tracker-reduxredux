from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import numpy as np
import pytest


def _tool() -> ModuleType:
    path = Path(__file__).parents[2] / "tools" / "evaluate_170330_capture_timing.py"
    spec = importlib.util.spec_from_file_location("evaluate_170330_capture_timing_tool", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_parabolic_peak_recovers_fractional_vertex() -> None:
    tool = _tool()

    offset, score = tool.parabolic_peak(
        np.asarray((1.0, 4.0, 3.0)),
        np.asarray((-1.0, 0.0, 1.0)),
    )

    assert offset == pytest.approx(0.25)
    assert score == pytest.approx(4.0)


def test_quadratic_metrics_remove_declared_track_model() -> None:
    tool = _tool()
    times = np.linspace(0.0, 4.0, 41)
    phases = 2_200.0 + 45.0 * times - 0.55 * times**2

    result = tool.quadratic_metrics(times, phases)

    assert result["count"] == 41
    assert result["rms_ns"] == pytest.approx(0.0, abs=1e-8)
    assert result["p90_absolute_ns"] == pytest.approx(0.0, abs=1e-8)


def test_lobe_width_interpolates_both_crossings() -> None:
    tool = _tool()
    offsets = np.arange(-5.0, 6.0)
    scores = np.exp(-0.5 * (offsets / 2.0) ** 2)

    width_ns = tool.lobe_width_ns(scores, offsets)

    assert width_ns == pytest.approx(719.12696, rel=1e-6)


def test_claim_configuration_freezes_both_capture_bindings(tmp_path: Path) -> None:
    tool = _tool()

    cases = tool.case_configs(tmp_path)

    assert set(cases) == {"old_20260826", "new_20260827"}
    assert str(cases["new_20260827"]["capture_root"]).endswith("cap-20260827T170330-a555a5cf5306")
    assert cases["old_20260826"]["phase_range_samples"] == (1500.0, 2500.0)


def test_json_normalization_removes_last_bit_float_noise() -> None:
    tool = _tool()
    lower = 0.30369967849829554
    upper = 0.3036996784982956

    assert tool.normalize_for_json(lower) == tool.normalize_for_json(upper)
