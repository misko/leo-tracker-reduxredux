"""Normalized radio polynomial background is independent of orbit hypotheses."""

import importlib
import sys
from pathlib import Path

import numpy as np
import pytest


@pytest.fixture
def tool():
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
    try:
        yield importlib.import_module("dsx01_smooth_background")
    finally:
        sys.path.pop(0)


def test_polynomial_background_density_matches_direct_covariance_integration(tool):
    t = np.linspace(0, 10, 15)
    y, noise = 1200 + 100 * t + 2 * t**2, np.full(15, 60.0)
    result = tool.background_logprob(y, t, noise)
    z = (t - 5) / 5
    basis = np.polynomial.legendre.legvander(z, 4)
    scale = np.array([1 / 4.4e-6 / np.sqrt(12), 15000, 30000, 15000, 7500])
    costs = []
    for degree in range(1, 5):
        u = basis[:, : degree + 1] * scale[: degree + 1]
        covariance = np.diag(noise**2) + u @ u.T
        costs.append(
            y @ np.linalg.solve(covariance, y)
            + np.linalg.slogdet(covariance)[1]
            + len(y) * np.log(2 * np.pi)
        )
    expected = np.logaddexp.reduce(np.log([0.4, 0.3, 0.2, 0.1]) - np.array(costs) / 2)
    np.testing.assert_allclose(result["log_probability"], expected, atol=1e-7)
    np.testing.assert_allclose(sum(result["degree_posterior"]), 1)
