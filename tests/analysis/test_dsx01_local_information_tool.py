"""Curvature of minus twice log likelihood has covariance 2/H."""

import importlib
import sys
from pathlib import Path

import numpy as np
import pytest


@pytest.fixture
def tool():
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
    try:
        yield importlib.import_module("probe_dsx01_local_information")
    finally:
        sys.path.pop(0)


def test_elliptical_log_likelihood_recovers_covariance_and_gradient(tool):
    covariance = np.array([[2.0, 0.7], [0.7, 1.0]])
    inverse = np.linalg.inv(covariance)
    mean = np.array([0.2, -0.4])
    x = np.array([0.8, -0.3])
    result = tool.local_curvature(lambda z: (z - mean) @ inverse @ (z - mean) + 20, x)
    np.testing.assert_allclose(result["formal_covariance_km2"], covariance, atol=1e-11)
    np.testing.assert_allclose(result["gradient"], 2 * inverse @ (x - mean), atol=1e-11)


def test_nonconvex_objective_does_not_produce_a_confidence_ellipse(tool):
    result = tool.local_curvature(lambda z: z[0] ** 2 - z[1] ** 2, np.zeros(2))
    assert result["formal_covariance_km2"] is None
