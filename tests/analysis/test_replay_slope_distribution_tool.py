from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import numpy as np
import pytest


def _tool() -> ModuleType:
    path = Path(__file__).parents[2] / "tools" / "report_replay_slope_distribution.py"
    spec = importlib.util.spec_from_file_location("replay_slope_distribution_tool", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_linear_slope_is_penultimate_coefficient_for_every_supported_degree() -> None:
    tool = _tool()

    assert tool._linear_slope_hz_s((12.0, 3.0)) == 12.0
    assert tool._linear_slope_hz_s((0.5, -2_000.0, 9.0)) == -2_000.0
    assert tool._linear_slope_hz_s((0.2, 0.5, -3_000.0, 9.0)) == -3_000.0


def test_linear_slope_rejects_invalid_or_nonfinite_polynomials() -> None:
    tool = _tool()

    with pytest.raises(ValueError, match="two to four"):
        tool._linear_slope_hz_s((1.0,))
    with pytest.raises(ValueError, match="finite"):
        tool._linear_slope_hz_s((np.inf, 0.0))


def test_common_histogram_edges_cover_every_slope_at_fixed_width() -> None:
    tool = _tool()
    rows = [
        {"linear_slope_hz_s": -9_057.0},
        {"linear_slope_hz_s": -2_095.0},
    ]

    edges = tool._common_edges(rows)

    assert edges[0] <= -9_057.0
    assert edges[-1] >= -2_095.0
    assert np.all(np.diff(edges) == tool.BIN_WIDTH_HZ_S)
