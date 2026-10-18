"""Causal phase scales compose with wide receiver drift without changing data."""

import importlib
import sys
from pathlib import Path

import numpy as np
from test_dsx01_rf_clock_tool import problem_inputs


def test_causal_phase_scale_changes_only_phase_prior_and_preserves_wide_initialization():
    path = str(Path(__file__).resolve().parents[2] / "tools")
    sys.path.insert(0, path)
    try:
        tool = importlib.import_module("prototype_dsx01_wide_causal_phase")
    finally:
        sys.path.remove(path)
    scan, seed = problem_inputs()
    scan.sky["phase_sigma_s"] = np.array([0.2])
    seed["state"]["beta"][4:8] = 150 * np.array([-12.0, -11.6, -9.0, -8.9])
    a = tool.causal_problem(scan, seed, "shared_phase", False, (0, 0), mode="floor1")
    b = tool.causal_problem(scan, seed, "shared_phase", False, (0, 0), mode="causal_gaussian")
    np.testing.assert_allclose(b.decode(b.initial)["beta"][4:8] / 150, [-12, -11.6, -9, -8.9])
    x = a.initial.copy()
    k = next(k for k, (key, _) in enumerate(a.coordinates) if key[0] == "phases")
    x[k] = 0.6
    ra, rb = a.residual(x), b.residual(x)
    expected = ra.copy()
    expected[b.phase_slice] *= 5
    np.testing.assert_allclose(rb, expected)
    np.testing.assert_array_equal(a.lower, b.lower)
    np.testing.assert_array_equal(a.upper, b.upper)
