"""Unit/linear-trend invariants for the within-window uncertainty proxy."""

import importlib
import sys
from pathlib import Path

import numpy as np
import pytest


@pytest.fixture
def tool():
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
    try:
        yield importlib.import_module("probe_dsx01_window_uncertainty")
    finally:
        sys.path.pop(0)


def test_true_frequency_and_chirp_do_not_inflate_the_scatter_proxy(tool):
    t = np.arange(15) / 750 - 0.01
    residual = np.random.default_rng(8).normal(0, 20, len(t))
    a = tool.frame_scatter(t, residual, np.full(len(t), 0.1))
    b = tool.frame_scatter(t, 120 + 1800 * t + residual, np.full(len(t), 0.1))
    np.testing.assert_allclose(a["variance_feature_hz2"], b["variance_feature_hz2"], rtol=1e-13)


def test_frequency_noise_scaling_has_squared_units(tool):
    t = np.arange(15) / 750 - 0.01
    residual = np.random.default_rng(13).normal(0, 30, len(t))
    a = tool.frame_scatter(t, residual, np.full(len(t), 0.1))
    b = tool.frame_scatter(t, 2 * residual, np.full(len(t), 0.1))
    np.testing.assert_allclose(b["variance_feature_hz2"], 4 * a["variance_feature_hz2"], rtol=1e-13)


def test_insufficient_quality_or_time_support_is_explicit(tool):
    assert tool.frame_scatter(np.arange(4) / 750, np.zeros(4), np.ones(4)) is None
    assert tool.frame_scatter(np.arange(15) / 750, np.zeros(15), np.zeros(15)) is None


def test_variable_noise_student_cost_includes_correct_diagonal_volume(tool):
    model = importlib.import_module("dsx01_window_noise")
    y, sigma = np.array([40.0, -80.0, 120.0, -60.0]), np.array([40.0, 80.0, 160.0, 120.0])
    groups = np.array([0, 0, 1, 1])
    result = model.window_student(y, np.empty((4, 0)), sigma, groups)
    expected = (
        sum(6 * np.log1p(np.sum((y[groups == g] / sigma[groups == g]) ** 2) / 4) for g in (0, 1))
        + 2 * np.log(sigma / 40).sum()
    )
    np.testing.assert_allclose(result["residual"] @ result["residual"], expected, rtol=1e-12)


def test_constant_point_noise_preserves_original_joint_posterior_coefficients(tool):
    model = importlib.import_module("dsx01_window_noise")
    rng = np.random.default_rng(94)
    y, u = rng.normal(0, 100, 20), rng.normal(0, 50, (20, 3))
    groups = np.repeat([0, 1], 10)
    original = model.student_joint_bound(y, u, 100.0, groups)
    updated = model.window_student(y, u, np.full(20, 100.0), groups)
    np.testing.assert_array_equal(updated["coefficient"], original["coefficient"])
    np.testing.assert_allclose(
        updated["residual"] @ updated["residual"] - original["residual"] @ original["residual"],
        40 * np.log(100 / 40),
    )


def test_precise_window_uses_the_same_likelihood_and_normalization(tool, monkeypatch):
    model = importlib.import_module("dsx01_precise_window")
    original = importlib.import_module("dsx01_robust_joint")
    rng = np.random.default_rng(102)
    n = 30
    y, u = rng.normal(0, 100, n), rng.normal(0, 50, (n, 5))
    sigma, groups = np.linspace(40, 180, n), np.repeat([0, 1, 2], 10)
    p = object.__new__(model.PreciseWindow)
    p.values, p.q = y, np.ones(n)
    p.point_noise, p.noise_groups = sigma, groups
    p.diagonal_logvolume = float(2 * np.log(sigma / 40).sum())
    monkeypatch.setattr(
        model.JointMarginal, "calculate", lambda self, x: dict(features=u, intercept=np.zeros(n))
    )
    expected = original.student_joint_bound(y, u, sigma, groups, iterations=256)
    actual = p.calculate(np.zeros(2))
    np.testing.assert_allclose(actual["coefficient"], expected["coefficient"], atol=1e-10)
    np.testing.assert_allclose(
        actual["residual"] @ actual["residual"],
        expected["residual"] @ expected["residual"] + p.diagonal_logvolume,
    )
