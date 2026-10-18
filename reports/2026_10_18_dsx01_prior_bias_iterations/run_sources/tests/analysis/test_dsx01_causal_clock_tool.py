"""Per-satellite causal phase scales compose with integrated frequency bias."""

import importlib
import sys
from pathlib import Path

import numpy as np
from test_dsx01_rf_clock_tool import problem_inputs


def test_phase_sigma_changes_only_prior_after_radio_and_clock_covariance():
    path = str(Path(__file__).resolve().parents[2] / "tools")
    sys.path.insert(0, path)
    try:
        tool = importlib.import_module("prototype_dsx01_causal_clock")
    finally:
        sys.path.remove(path)
    scan, seed = problem_inputs()
    scan.sky["phase_sigma_s"] = np.array([0.2])
    a = tool.clock_problem(
        scan, seed, "shared_phase", False, (0, 0), phase_mode="floor", clock_sigma=5000
    )
    b = tool.clock_problem(
        scan, seed, "shared_phase", False, (0, 0), phase_mode="causal", clock_sigma=5000
    )
    tool.lock_aliases(b, [1] * 4)
    assert b.problem.problem.alias == [1] * 4
    tool.lock_aliases(b, a.alias)
    x = a.initial.copy()
    k = next(k for k, (key, _) in enumerate(a.coordinates) if key[0] == "phases")
    x[k] = 0.4
    ra, rb = a.residual(x), b.residual(x)
    expected = ra.copy()
    expected[b.phase_slice] *= 5
    np.testing.assert_allclose(rb, expected)
    np.testing.assert_allclose(a.predicted(x)[0], b.predicted(x)[0])
    assert len(a.initial) == len(b.initial)
