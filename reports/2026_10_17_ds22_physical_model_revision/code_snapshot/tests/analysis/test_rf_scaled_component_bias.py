"""Fractional carrier bias profiles obey the dense Gaussian normal equations."""

import numpy as np
import pytest

from leo.analysis.research.component_frequency_bias import profile_component_bias
from leo.analysis.research.rf_scaled_component_bias import profile_rf_scaled_bias


def statistics(q):
    n = np.array([20, 30])
    return dict(
        q=np.asarray(q),
        ci=np.array([0, 0]),
        starts=np.array([0]),
        n=n,
        count=np.array([sum(n)]),
        g=np.array([0, 1]),
        mx=np.array([0.1, 0.3]),
        mean=np.array([[720.0, 5000.0], [880.0, 6000.0]]),
        rss=np.full((2, 2), 20000.0),
        xx=np.array([2.0, 5.0]),
        xz=np.zeros((2, 2)),
        component_visible=np.array([[True, True]]),
    )


def test_unit_rf_exactly_matches_native_bias_model():
    stats = statistics([1.0, 1.0])
    beta = np.arange(8.0)
    a = profile_component_bias(stats, beta, bias_sigma_hz=1000)
    b = profile_rf_scaled_bias(stats, beta, bias_sigma_hz=1000)
    for name in ("best", "rms_hz", "aliases", "score", "bias_hz", "residual_mse"):
        np.testing.assert_allclose(getattr(a, name), getattr(b, name))


def test_scaled_coefficient_and_log_determinant_match_dense_gaussian():
    stats = statistics([0.9, 1.1])
    result = profile_rf_scaled_bias(stats, np.zeros(8), bias_sigma_hz=1000)
    expected = sum(stats["n"] * stats["q"] * stats["mean"][:, 0]) / (
        sum(stats["n"] * stats["q"] ** 2) + 150**2 / 1000**2
    )
    assert result.bias_hz[0, 0] == pytest.approx(expected)
    # Dense marginal covariance gives the same quadratic and determinant term.
    q = np.repeat(stats["q"], stats["n"])
    values = np.repeat(stats["mean"][:, 0], stats["n"])
    covariance = 150.0**2 * np.eye(50) + 1000.0**2 * np.outer(q, q)
    quadratic = 150.0**2 * values @ np.linalg.solve(covariance, values)
    _, logdet = np.linalg.slogdet(covariance / 150.0**2)
    expected_score = (quadratic + 40000 + 150.0**2 * logdet) / 50
    assert result.score[0, 0] == pytest.approx(expected_score, rel=1e-9)
    assert result.rms_hz[0] < 30


def test_native_alias_spacing_and_zero_bias_are_unchanged():
    stats = statistics([0.9, 1.1])
    stats["mean"][0] += 3 / 4.4e-6
    stats["mean"][1] -= 2 / 4.4e-6
    a = profile_component_bias(stats, np.zeros(8), bias_sigma_hz=0)
    b = profile_rf_scaled_bias(stats, np.zeros(8), bias_sigma_hz=0)
    np.testing.assert_allclose(a.score, b.score)
    assert b.aliases[:, 0].tolist() == [-3, 2]
    with pytest.raises(ValueError):
        profile_rf_scaled_bias(dict(stats, q=[0, 1]), np.zeros(8), bias_sigma_hz=1000)
