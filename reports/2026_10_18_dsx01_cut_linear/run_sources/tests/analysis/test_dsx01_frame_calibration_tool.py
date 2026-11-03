"""Relative calibration uses a robust line without a satellite prediction."""

import importlib
import sys
from pathlib import Path

import numpy as np


def test_relative_line_recovers_drift_with_sparse_bad_source_pairs():
    path = str(Path(__file__).resolve().parents[2] / "tools")
    sys.path.insert(0, path)
    try:
        tool = importlib.import_module("probe_dsx01_frame_coherent_calibration")
    finally:
        sys.path.remove(path)
    times = np.linspace(10, 290, 100)
    y = 26000 - 8.5 * (times - 150)
    y[::13] += 12000
    fit = tool.fit_line(times, y)
    assert abs(fit["coefficients"][0] - 26000) < 30
    assert abs(fit["coefficients"][1] + 8.5) < 0.05
