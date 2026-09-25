from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import numpy as np


def _tool() -> ModuleType:
    path = Path(__file__).parents[2] / "tools" / "report_d3_d4_qin_weighted_cfo.py"
    spec = importlib.util.spec_from_file_location("report_d3_d4_qin_weighted_cfo_tool", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_qin_quality_requires_exact_strength_and_control_margin() -> None:
    tool = _tool()
    frames = [
        {"train_exact_score": 0.80, "train_margin": 0.70},
        {"train_exact_score": 0.80, "train_margin": 0.01},
        {"train_exact_score": 0.08, "train_margin": 0.07},
        {"train_exact_score": 0.80, "train_margin": -0.01},
    ]

    quality = tool.qin_frame_quality(frames)

    assert quality[0] > quality[1]
    assert quality[0] > quality[2]
    assert quality[3] == 0.0
    assert np.all((quality >= 0.0) & (quality <= 1.0))


def test_frame_opacity_is_monotonic_and_nonzero() -> None:
    tool = _tool()
    colors = tool.frame_rgba(np.asarray([0.0, 0.5, 1.0]))

    assert colors.shape == (3, 4)
    assert 0.0 < colors[0, 3] < colors[1, 3] < colors[2, 3] <= 1.0


def test_selects_exactly_d3_and_d4() -> None:
    tool = _tool()
    document = {
        "dwells": [
            {"spec": {"label": "D2 · before"}},
            {"spec": {"label": "D3 · first"}},
            {"spec": {"label": "D4 · second"}},
            {"spec": {"label": "D5 · after"}},
        ]
    }

    d3, d4 = tool.select_d3_d4(document)

    assert d3["spec"]["label"].startswith("D3 ")
    assert d4["spec"]["label"].startswith("D4 ")
