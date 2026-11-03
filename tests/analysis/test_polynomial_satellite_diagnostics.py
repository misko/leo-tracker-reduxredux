"""All-candidate residual screening agrees with the original scalar oracle."""

import importlib
from pathlib import Path

import numpy as np

from leo.analysis.research.polynomial_satellite_diagnostics import (
    batch_noise_screen,
    feasible_order,
    orbit_shape_lower_bounds,
)


def test_batch_gates_match_scalar_screen_for_noise_trends_steps_and_curvature(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "tools"))
    scalar = importlib.import_module("analyze_dsx01_fixed_site").noise_screen
    rng = np.random.default_rng(773)
    for n in (6, 20, 80):
        t = np.sort(rng.uniform(0, 120, n))
        r = rng.normal(0, 90, (12, n))
        r[0] += 500
        r[1] += 30 * (t - t.mean())
        r[2, n // 2 :] += 600
        r[3] += 0.5 * (t - t.mean()) ** 2
        batch = batch_noise_screen(r, t)
        for index, row in enumerate(r):
            old = scalar(row, t)
            for key, value in old.items():
                np.testing.assert_allclose(batch[key][index], value, atol=1e-9)


def test_noise_screen_can_recover_valid_runner_up_without_relaxing_any_gate():
    t = np.arange(100.0)
    x = t - t.mean()
    r = np.stack([0.5 * x**2, np.random.default_rng(773).normal(0, 20, len(t))])
    r[0] -= r[0].mean()
    score = np.array([1.0, 2.0, 3.0])
    ordered, _ = feasible_order(score, np.array([True, True, False]), r, t)
    assert ordered.tolist() == [1]


def test_affine_diagnostic_removes_slope_and_loses_identity_discrimination():
    t = np.arange(50.0)
    f = np.stack([1000 - 50 * t + 0.1 * t * t, -300 + 60 * t + 0.1 * t * t])
    y = f[0] + 400 + 2 * (t - t.mean())
    values = orbit_shape_lower_bounds(y, t, f)
    np.testing.assert_allclose(values["mean_hz"][0], 400)
    np.testing.assert_allclose(values["slope_hz_s"][0], 2)
    assert values["rms_offset_hz"][0] > 20
    np.testing.assert_allclose(values["rms_affine_hz"], 0, atol=1e-5)
