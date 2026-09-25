from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import numpy as np


def _tool() -> ModuleType:
    tools_root = Path(__file__).parents[2] / "tools"
    sys.path.insert(0, str(tools_root))
    path = tools_root / "report_470384_direct_frame_cfo.py"
    spec = importlib.util.spec_from_file_location("report_470384_direct_frame_cfo_tool", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_direct_absolute_cfo_search_recovers_raw_frame_frequency() -> None:
    tool = _tool()
    rng = np.random.default_rng(8)
    positions = np.sort(rng.choice(np.arange(100, 3_200), size=1_500, replace=False))
    expected_hz = 428_347.0
    products = np.exp(
        2j * np.pi * expected_hz * positions / tool.semicoherent.SAMPLE_RATE_HZ
    )

    frequency, score, boundary = tool.optimize_absolute_cfo(
        products,
        float(len(products) ** 2),
        positions,
        center_cfo_hz=425_000.0,
    )

    assert abs(frequency - expected_hz) <= 1.0
    assert score > 0.99
    assert not boundary


def test_direct_absolute_cfo_search_reports_coarse_boundary() -> None:
    tool = _tool()
    positions = np.arange(100, 3_200)
    expected_hz = 431_000.0
    products = np.exp(
        2j * np.pi * expected_hz * positions / tool.semicoherent.SAMPLE_RATE_HZ
    )

    frequency, _score, boundary = tool.optimize_absolute_cfo(
        products,
        float(len(products) ** 2),
        positions,
        center_cfo_hz=425_000.0,
    )

    assert abs(frequency - expected_hz) <= 1.0
    assert boundary
