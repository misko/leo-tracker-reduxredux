"""Numerical contracts for fixed-family geographic diagnostics."""

import numpy as np
import pytest

from leo.analysis.research.continuous_curve_fit import (
    bounded_gauss_newton,
    paired_phase_frequency,
    project_curve,
    robust_curve,
)
from leo.analysis.research.orbit_phase_geometry import phase_frequency_grid


def test_paired_geometry_matches_dense_phase_grid_and_refuses_extrapolation():
    knots = np.arange(-20, 321, 5.0)
    position = np.zeros((2, len(knots), 3))
    position[..., 0] = -2600 + np.array([0, 200])[:, None]
    position[..., 1] = -4800 + 4 * knots
    position[..., 2] = 4200 + 2 * knots
    velocity = np.broadcast_to([0, 4.0, 2.0], position.shape).copy()
    bank = dict(time_s=knots, position_km=position, velocity_km_s=velocity)
    times, labels, phases = (
        np.array([3.0, 70, 180, 180]),
        np.array([1, 0, 1, 0]),
        np.array([2.1, -3.7]),
    )
    f, e = paired_phase_frequency(bank, times, labels, phases, 37.906, -122.545)
    ff, ee = phase_frequency_grid(bank, times, 37.906, -122.545, phase_seconds=phases)
    np.testing.assert_allclose(f, ff[labels, np.arange(len(times))], atol=1e-8)
    np.testing.assert_allclose(e, ee[labels, np.arange(len(times))], atol=1e-10)
    with pytest.raises(ValueError):
        paired_phase_frequency(bank, np.array([400.0]), np.array([0]), phases, 37.906, -122.545)


def test_gaussian_constant_profile_matches_augmented_least_squares():
    rng = np.random.default_rng(943)
    t = np.arange(15.0)
    raw = 1900 + rng.normal(0, 150, len(t))
    w = np.diag(1 / np.linspace(110, 200, len(t)))
    z = project_curve(raw, w, t)
    one = w @ np.ones(len(t))
    bias = np.linalg.lstsq(np.r_[one, 0.001][:, None], np.r_[w @ raw, 0.0], rcond=None)[0][0]
    expected = np.sum((w @ (raw - bias)) ** 2) + (bias / 1000) ** 2
    assert z @ z == pytest.approx(expected)


def test_affine_projection_keeps_actual_curved_shape_and_removes_drift():
    t = np.linspace(12, 240, 28)
    w = np.eye(len(t)) / 150
    curve = 0.04 * (t - t.mean()) ** 2
    a = project_curve(curve, w, t, affine=True)
    b = project_curve(curve + 17300 - 2.3 * t, w, t, affine=True)
    np.testing.assert_allclose(a, b, atol=1e-12)
    assert np.linalg.norm(a) > 1


def test_smooth_curve_cost_has_no_threshold_jump():
    costs = []
    for rms in (449.999, 450, 450.001):
        z = robust_curve(np.full(40, rms / 150), 40)
        costs.append(z @ z)
    assert costs[0] < costs[1] < costs[2]
    assert costs[2] - costs[0] < 0.001


def test_bounded_solver_recovers_anisotropic_position_and_respects_box():
    def residual(x):
        return np.array([3 * (x[0] - 1.25), 0.5 * (x[1] + 2.75), x[0] + x[1] + 1.5])

    fit = bounded_gauss_newton(residual, [7, 7], [-12.5, -12.5], [12.5, 12.5])
    np.testing.assert_allclose(fit["parameters"], [1.25, -2.75], atol=1e-5)
    assert all(np.all(abs(r["parameters"]) <= 12.5) for r in fit["history"])
    scores = [r["score"] for r in fit["history"]]
    assert np.all(np.diff(scores) < 0)


def test_projection_rejects_nonfinite_or_invalid_dimensions():
    with pytest.raises(ValueError):
        project_curve(np.ones(4), np.eye(3), np.arange(4))
    with pytest.raises(ValueError):
        project_curve(np.full(4, np.nan), np.eye(4), np.arange(4))
