"""Prior substitution must preserve data and respect the original phase scale."""

import importlib
import sys
from pathlib import Path

import numpy as np
import pytest
from test_dsx01_rf_clock_tool import problem_inputs


@pytest.fixture
def tool():
    path = str(Path(__file__).resolve().parents[2] / "tools")
    sys.path.insert(0, path)
    try:
        yield importlib.import_module("prototype_dsx01_phase_priors")
    finally:
        sys.path.remove(path)


def test_causal_phase_scales_change_only_phase_prior_coordinates(tool):
    scan, seed = problem_inputs()
    scan.sky["phase_sigma_s"] = np.array([0.1])
    baseline = tool.CausalPhaseFamilies(scan, seed, "shared_phase", False, (0, 0), mode="floor1")
    causal = tool.CausalPhaseFamilies(scan, seed, "shared_phase", False, (0, 0))
    x = baseline.initial.copy()
    x[-1] = 0.2
    a, b = baseline.residual(x), causal.residual(x)
    mask = np.ones(len(a), bool)
    mask[causal.phase_slice] = False
    np.testing.assert_allclose(a[mask], b[mask])
    np.testing.assert_allclose(a[causal.phase_slice], 0.2)
    np.testing.assert_allclose(b[causal.phase_slice], 2)


def test_heavy_tailed_prior_limits_a_single_disagreeing_orbits_leverage(tool):
    scan, seed = problem_inputs()
    scan.sky["phase_sigma_s"] = np.array([0.1])
    gaussian = tool.CausalPhaseFamilies(scan, seed, "shared_phase", False, (0, 0))
    student = tool.CausalPhaseFamilies(
        scan, seed, "shared_phase", False, (0, 0), mode="causal_student"
    )
    x = gaussian.initial.copy()
    x[-1] = 1
    g, t = gaussian.residual(x)[gaussian.phase_slice], student.residual(x)[student.phase_slice]
    assert g @ g == pytest.approx(100)
    assert t @ t == pytest.approx(3 * np.log1p(100 / 3))
    assert t @ t < g @ g
