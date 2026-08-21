from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import numpy as np
import pytest


def _tool() -> ModuleType:
    path = Path(__file__).parents[2] / "tools" / "report_five_dwell_tle_cone.py"
    spec = importlib.util.spec_from_file_location("five_dwell_tle_cone_tool", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_linear_rate_is_polynomial_rate_at_reference_time() -> None:
    tool = _tool()

    assert tool._linear_rate_hz_s((12.0, 3.0)) == 12.0
    assert tool._linear_rate_hz_s((0.5, -2_000.0, 9.0)) == -2_000.0
    assert tool._linear_rate_hz_s((0.2, 0.5, -3_000.0, 9.0)) == -3_000.0


def test_linear_rate_rejects_invalid_or_nonfinite_polynomials() -> None:
    tool = _tool()

    with pytest.raises(ValueError, match="two to four"):
        tool._linear_rate_hz_s((1.0,))
    with pytest.raises(ValueError, match="finite"):
        tool._linear_rate_hz_s((np.inf, 0.0))


def test_track_rate_repeats_one_reference_time_estimate() -> None:
    tool = _tool()
    track = SimpleNamespace(
        row=SimpleNamespace(absolute_coefficients_hz=(0.2, 0.5, -3_000.0, 9.0))
    )

    rates = tool._track_rate(track, np.asarray([2.0, 3.0, 5.0]))

    np.testing.assert_array_equal(rates, [-3_000.0, -3_000.0, -3_000.0])
