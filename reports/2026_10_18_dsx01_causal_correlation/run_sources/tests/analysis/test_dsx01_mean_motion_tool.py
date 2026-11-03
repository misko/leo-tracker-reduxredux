"""Mean-motion uncertainty must move one shared orbit, with an explicit prior."""

import importlib
import sys
from pathlib import Path

import numpy as np
import pytest
from test_dsx01_rf_clock_tool import problem_inputs

from leo.analysis.research.orbit_phase_geometry import phase_frequency_grid


@pytest.fixture
def tool():
    path = str(Path(__file__).resolve().parents[2] / "tools")
    sys.path.insert(0, path)
    try:
        yield importlib.import_module("prototype_dsx01_mean_motion")
    finally:
        sys.path.remove(path)


def test_zero_and_shared_state_correction_match_dense_geometry_and_prior(tool):
    scan, seed = problem_inputs()
    base = tool.AnchoredFamilies(scan, seed, "shared_phase", False, (0, 0))
    dp = np.broadcast_to([100, -200, 50], scan.sky["position_km"][0].shape).copy()
    dv = np.broadcast_to([0.05, 0.1, 0], dp.shape).copy()
    p = tool.MotionFamilies(
        scan, seed, "shared_phase", False, (0, 0), sigma=0.002, basis={0: (dp, dv)}
    )
    np.testing.assert_allclose(p.predicted(p.initial)[0], base.predicted(base.initial)[0])
    np.testing.assert_allclose(p.residual(p.initial)[:-1], base.residual(base.initial))
    x = p.initial.copy()
    x[-1] = 0.5
    state = p.decode(x)
    assert state["mean_motion_offsets_rev_day"][0] == pytest.approx(0.001)
    bank = {k: v.copy() for k, v in scan.sky.items()}
    bank["position_km"][0] += 0.001 * dp
    bank["velocity_km_s"][0] += 0.001 * dv
    ff, ee = phase_frequency_grid(bank, p.flat_times, 37.906, -122.545)
    f, e = p.predicted(x)
    np.testing.assert_allclose(f, ff[p.flat_labels, np.arange(len(f))], atol=1e-8)
    np.testing.assert_allclose(e, ee[p.flat_labels, np.arange(len(e))], atol=1e-10)
    assert p.residual(x)[-1] == pytest.approx(0.5)


def test_radio_prior_composition_keeps_mean_motion_prior_and_shared_hardware(tool):
    scan, seed = problem_inputs()
    dp = np.zeros_like(scan.sky["position_km"][0])
    base = tool.MotionFamilies(scan, seed, "shared_phase", True, (0, 0), basis={0: (dp, dp)})
    p = tool.ReceiverDriftProblem(base, mean_sigma=10)
    x = p.initial.copy()
    x[-1] = 0.8
    x[p.pairs[0][0]] = 0.5
    r = p.residual(x)
    np.testing.assert_allclose(r[-6:-2], [0.5, 0, 0, 0])
    assert r[-1] == pytest.approx(0.8)


def test_reference_mean_motion_tangent_matches_exact_sgp4_at_nonzero_correction(tool):
    sat = tool.Satrec()
    sat.sgp4init(
        tool.WGS72,
        "i",
        100,
        28000.0,
        0.00003,
        0,
        0,
        0.0002,
        0.5,
        0.9,
        1.0,
        15.3 * 2 * np.pi / 1440,
        1.3,
    )
    elapsed = 0.5
    origin = int(((sat.jdsatepoch - 2440587.5) + sat.jdsatepochF + elapsed) * 86400e9 - 150e9)
    delta, step = 0.004, 0.001
    cat = tool.ElementSetCatalogue(
        ("base", "plus", "minus", "exact"),
        (100,) * 4,
        (sat, *(tool.reference_motion_satellite(sat, d, elapsed) for d in (step, -step, delta))),
    )
    times = np.arange(-20.0, 321.0, 5)
    p, v, good = tool.ecef_states(cat, origin, times)
    assert good.all()
    approx_p = p[0] + delta * (p[1] - p[2]) / (2 * step)
    approx_v = v[0] + delta * (v[1] - v[2]) / (2 * step)
    assert np.linalg.norm(approx_p - p[3], axis=1).max() < 0.01  # metres-to-10m scale
    bank = dict(
        time_s=times,
        position_km=np.array([approx_p, p[3]]),
        velocity_km_s=np.array([approx_v, v[3]]),
    )
    f, _ = phase_frequency_grid(bank, np.linspace(0, 300, 30), 37.906, -122.545, phase_seconds=0.4)
    assert np.max(abs(f[0] - f[1])) < 0.5


def test_exact_eccentricity_relinearization_preserves_original_parameter_priors(tool):
    exact = importlib.import_module("refine_dsx01_exact_receiver_orbits")
    scan, seed = problem_inputs()
    shape = scan.sky["position_km"][0].shape
    dp = np.zeros((2, *shape))
    dv = np.zeros_like(dp)
    dp[0, :, 0] = 1000
    dp[1, :, 1] = 2000
    scan.element_basis = lambda j: (dp, dv)
    reference = np.array([1e-4, -2e-4])
    bank = {k: v.copy() for k, v in scan.sky.items()}
    bank["position_km"][0] += np.einsum("k,ktd->td", reference, dp)
    p = exact.ExactReferenceFamilies(
        scan,
        seed,
        "orbit_em",
        False,
        (0, 0),
        reference_extra={0: reference},
        reference_geometry=(bank, {0: (dp, dv)}),
    )
    x = p.initial.copy()
    for k, (key, scale) in enumerate(p.coordinates):
        if key[0] == "extra":
            x[k] = reference[key[2]] / scale
    f, e = p.predicted(x)
    ff, ee = phase_frequency_grid(bank, p.flat_times, 37.906, -122.545)
    np.testing.assert_allclose(f, ff[p.flat_labels, np.arange(len(f))], atol=1e-8)
    np.testing.assert_allclose(e, ee[p.flat_labels, np.arange(len(e))], atol=1e-10)
    np.testing.assert_allclose(p.residual(x)[-2:], [1, -2])
