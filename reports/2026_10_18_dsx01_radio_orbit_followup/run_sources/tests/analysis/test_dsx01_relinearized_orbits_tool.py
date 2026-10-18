"""Absolute-prior and exact-state controls for physical relinearization."""

import importlib
import sys
from pathlib import Path

import numpy as np
import pytest
from sgp4.api import WGS72, Satrec


@pytest.fixture
def tool():
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
    try:
        yield importlib.import_module("dsx01_relinearized_orbits")
    finally:
        sys.path.pop(0)


def test_arbitrary_reference_changes_do_not_recenter_linear_absolute_prior(tool):
    rng = np.random.default_rng(49)
    intercept, h, u = rng.normal(size=19), rng.normal(size=19), rng.normal(size=(19, 5))
    for _ in range(3):
        phi, theta = rng.normal(size=19), rng.normal(size=(19, 5))
        at_reference = intercept + h * phi + np.sum(u * theta, axis=1)
        recovered = tool.absolute_intercept(at_reference, h, phi, u, theta)
        np.testing.assert_allclose(recovered, intercept, atol=2e-15)


def test_state_derivatives_leave_quadratic_remainder_and_preserve_tle_inputs(tool):
    sat = Satrec()
    sat.sgp4init(WGS72, "i", 12345, 26438.0, 0.0, 0.0, 0.0, 0.001, 0.3, 0.7, 0.1, 0.065, 0.2)
    source = sat.mo, sat.no_kozai, sat.ecco, sat.argpo
    origin, times = 1640995200000000000, np.arange(-10.0, 301.0, 30.0)
    scales = np.array([[0.001, 0.01, 0.01, 1e-4, 2e-4]])
    reference = np.array([[0.7, -0.3, 0.4, 0.5, -0.4]])
    direction = np.array([[0.05, -0.03, 0.02, 0.01, -0.01]])
    mean, modes = tool.reference_banks([sat], origin, times, scales, reference, [0])
    errors = []
    for factor in (1.0, 0.5):
        delta = factor * direction
        actual, _ = tool.reference_banks([sat], origin, times, scales, reference + delta, [0])
        linear = mean["position_km"] + np.einsum(
            "sk,sktd->std", delta, modes["position_km"].reshape(1, 5, -1, 3)
        )
        errors.append(np.linalg.norm(actual["position_km"] - linear))
    assert 3 < errors[0] / errors[1] < 5
    assert errors[0] < 1e-3
    np.testing.assert_array_equal(source, [sat.mo, sat.no_kozai, sat.ecco, sat.argpo])


def test_prior_scale_and_reference_dimensions_are_checked(tool):
    with pytest.raises(ValueError, match="reference"):
        tool.absolute_intercept(
            np.ones(3), np.ones(3), np.ones(3), np.ones((3, 5)), np.ones((3, 3))
        )
