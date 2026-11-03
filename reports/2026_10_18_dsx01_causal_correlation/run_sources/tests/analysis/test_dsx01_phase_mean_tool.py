"""Forecasted means alter only phase-prior residuals, retaining native dynamics."""

import importlib
import sys
from pathlib import Path

import numpy as np
from test_dsx01_rf_clock_tool import problem_inputs


def test_nonzero_mean_changes_only_phase_prior_and_zero_mean_is_exact_control():
    path = str(Path(__file__).resolve().parents[2] / "tools")
    sys.path.insert(0, path)
    try:
        tool = importlib.import_module("prototype_dsx01_phase_forecast")
    finally:
        sys.path.remove(path)
    scan, seed = problem_inputs()
    p = tool.geometry_problem(
        scan, seed, "shared_phase", False, (0, 0), mean_sigma=10, height_sigma=0
    )
    zero = tool.PhaseMeanProblem(p, {})
    shift = tool.PhaseMeanProblem(p, {"100": 0.6})
    x = p.initial.copy()
    np.testing.assert_allclose(zero.residual(x), p.residual(x))
    expected = p.residual(x)
    expected[shift.phase_slice] -= 0.6
    np.testing.assert_allclose(shift.residual(x), expected)
    np.testing.assert_allclose(shift.predicted(x)[0], p.predicted(x)[0])
    np.testing.assert_array_equal(shift.lower, p.lower)
    np.testing.assert_array_equal(shift.upper, p.upper)
