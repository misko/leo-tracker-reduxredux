"""Shared latent orbit corrections and radio-coordinate composition."""

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
        yield importlib.import_module("prototype_dsx01_orbit_marginal")
    finally:
        sys.path.remove(path)


def prepared(tool):
    scan, seed = problem_inputs()
    base = tool.AnchoredFamilies(scan, seed, "shared_phase", False, (0, 0))
    f, _ = base.predicted(base.initial)
    for t, block in zip(scan.tracks, base.slices, strict=True):
        t["values"] = t["rf_hz"] / 11.5e9 * f[block]
    dp = np.zeros_like(scan.sky["position_km"])
    dv = np.zeros_like(dp)
    dp[0, :, 0] = 0.002 * (scan.sky["time_s"] - 150) ** 2
    dv[0, :, 0] = 0.004 * (scan.sky["time_s"] - 150)
    modes = dict(time_s=scan.sky["time_s"], position_km=dp, velocity_km_s=dv)
    return scan, seed, modes


def test_one_conditional_orbit_correction_is_shared_across_receivers_and_channels(tool):
    scan, seed, modes = prepared(tool)
    scan.tracks[0]["values"] += np.linspace(-600, 600, 31)
    p = tool.MarginalFamilies(
        scan,
        seed,
        "shared_phase",
        False,
        (0, 0),
        kind="old_new",
        provided_modes=(modes, {0: dict(norad=100)}),
    )
    state = p.association_state(p.initial)
    coefficient = state["marginal_orbit_coefficients"][0]
    assert coefficient.shape == (1,) and abs(coefficient[0]) > 1e-6
    f, _ = p.predicted(p.initial)
    nominal, _ = super(tool.MarginalFamilies, p).predicted(p.initial)
    corrections = [(f - nominal)[sl] for sl in p.slices]
    for c in corrections[1:]:
        np.testing.assert_allclose(c, corrections[0])


def test_association_state_maps_wider_receiver_coordinates_before_conditioning(tool):
    scan, seed, modes = prepared(tool)
    base = tool.MarginalFamilies(
        scan, seed, "shared_phase", True, (0, 0), kind="old_new", provided_modes=(modes, {})
    )
    p = tool.ReceiverDriftProblem(base, mean_sigma=10)
    x = p.initial.copy()
    x[p.pairs[0][0]] = 0.8
    state = p.association_state(x)
    np.testing.assert_allclose(state["beta"][4:6] / 150, [8, 8])
    assert 0 in state["marginal_orbit_coefficients"]
    r = p.residual(x)
    start = len(r) - len(p.labels) - 4
    np.testing.assert_allclose(r[start : start + 4], [0.8, 0, 0, 0])


def test_whole_family_clutter_probability_does_not_force_a_bad_candidate(tool):
    scan, seed, _ = prepared(tool)
    for t in scan.tracks:
        t["values"] += 10000 * np.sin(t["times"] / 8)
    p = tool.MarginalFamilies(
        scan, seed, "shared_phase", False, (0, 0), kind="none", likelihood="mixture"
    )
    state = p.association_state(p.initial)
    assert state["marginal_signal_probability"][0] < 1e-6
    assert not state["marginal_orbit_coefficients"]
    assert np.isfinite(p.residual(p.initial)).all()


def test_shared_satellite_clock_bias_scales_with_rf_without_new_fitted_coordinates(tool):
    scan, seed, _ = prepared(tool)
    for t in scan.tracks:
        t["values"] += t["rf_hz"] / 11.5e9 * 2000
    baseline = tool.AnchoredFamilies(scan, seed, "shared_phase", False, (0, 0))
    p = tool.MarginalFamilies(
        scan,
        seed,
        "shared_phase",
        False,
        (0, 0),
        kind="none",
        curve_bias_sigma=300,
        satellite_bias_sigma=5000,
    )
    assert len(p.initial) == len(baseline.initial)
    state = p.association_state(p.initial)
    bias = state["marginal_satellite_bias_hz"][0]
    assert 1900 < bias < 2100
    f, _ = p.predicted(p.initial)
    nominal, _ = baseline.predicted(baseline.initial)
    np.testing.assert_allclose(f - nominal, bias, atol=1e-8)
    assert not state["marginal_orbit_coefficients"]
