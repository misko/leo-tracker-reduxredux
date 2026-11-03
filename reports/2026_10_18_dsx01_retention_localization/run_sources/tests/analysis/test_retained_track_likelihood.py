import numpy as np
import pytest

from leo.analysis.research.retained_track_likelihood import (
    NOISE,
    PERIOD,
    add_curve,
    profile,
    projected_receiver_basis,
    whitening,
)
from leo.analysis.research.shared_satellite_correction import profile_curve


def test_white_model_equals_existing_native_alias_and_gaussian_bias_profile():
    t = np.linspace(0, 60, 80)
    f = np.array([t**2, 2 * t**2])
    y = t**2 + PERIOD + 120 + 20 * np.sin(t)
    w, volume = whitening(t)
    result, old = profile(y, f, w, volume), profile_curve(y, f)
    np.testing.assert_array_equal(result["alias"], old["aliases"])
    np.testing.assert_allclose(result["residual"], old["residual"], atol=1e-8)
    np.testing.assert_allclose(result["cost"], old["score"] * len(t) / NOISE**2, atol=1e-8)


def test_ou_whitens_declared_covariance_without_changing_observation_count():
    t = np.array([0.0, 0.3, 0.7, 2.0, 5.0, 10.0])
    w, volume = whitening(t, correlated_sigma_hz=150, correlation_seconds=10)
    covariance = np.eye(len(t)) * NOISE**2 + 150**2 * np.exp(-abs(t[:, None] - t) / 10)
    np.testing.assert_allclose(w @ covariance @ w.T, np.eye(len(t)), atol=1e-12)
    assert volume > 0
    assert profile(t, t, w, volume)["residual"].shape == (1, len(t))


def test_receiver_smooth_basis_has_no_affine_projection():
    t = np.linspace(0, 300, 301)
    basis = projected_receiver_basis(t)
    np.testing.assert_allclose(np.column_stack((np.ones(len(t)), t - 150)).T @ basis, 0, atol=1e-9)


def test_curve_elimination_matches_explicit_gaussian_bias_normal_equations():
    t = np.linspace(0, 30, 31)
    x = np.column_stack((t, t**2))
    y = 2 * t + 0.1 * t**2 + 30
    w, _ = whitening(t)
    normal, rhs = np.zeros((2, 2)), np.zeros(2)
    add_curve(normal, rhs, x, y, w)
    full = np.column_stack((x, np.ones(len(t)))) / NOISE
    explicit = full.T @ full
    explicit[2, 2] += 1 / 1000**2
    target = full.T @ (y / NOISE)
    np.testing.assert_allclose(
        np.linalg.solve(normal, rhs), np.linalg.solve(explicit, target)[:2], atol=1e-10
    )


def test_duplicate_times_rejected():
    with pytest.raises(ValueError):
        whitening([0, 0, 1])
