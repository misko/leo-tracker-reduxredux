"""Validate exact fixed-endpoint score accounting without running any fit."""

import importlib.util
from pathlib import Path

import numpy as np
import pytest

SPEC = importlib.util.spec_from_file_location(
    "geometry_endpoint_audit", Path(__file__).with_name("endpoint_audit.py"))
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)


def test_reweight_matches_direct_quadratic_and_ignores_other_clock_terms():
    direction = np.array([3.0, 4.0]) / 5
    projector = np.outer(direction, direction)
    physical = np.array([0.7, -0.2])
    fit = dict(vector=[0.0] * 10,
               clock_coefficients=[9000.0, *list(100 * physical), 7000.0, 8000.0])
    geometry = dict(projector=projector, protected_sigma_hz_s=0.25, wide_sigma_hz_s=0.5)
    uniform_precision = np.eye(2) / 0.5**2
    protected_precision = uniform_precision + (1 / 0.25**2 - 1 / 0.5**2) * projector
    expected = 0.5 * physical @ (protected_precision - uniform_precision) @ physical
    assert AUDIT.extra_penalty(fit, geometry) == pytest.approx(expected)
    # RF-time and receiver-clock entries must not affect the extracted slope penalty.
    fit["clock_coefficients"][0] = -1e9
    fit["clock_coefficients"][-2:] = [-1e9, 1e9]
    assert AUDIT.extra_penalty(fit, geometry) == pytest.approx(expected)


def test_zero_projector_and_equal_sigmas_add_no_penalty():
    fit = dict(vector=[0.0] * 10, clock_coefficients=[20.0, 30.0, 1.0, 2.0])
    geometry = dict(projector=np.zeros((2, 2)),
                    protected_sigma_hz_s=0.25, wide_sigma_hz_s=0.5)
    assert AUDIT.extra_penalty(fit, geometry) == 0
    geometry.update(projector=np.eye(2), protected_sigma_hz_s=0.5)
    assert AUDIT.extra_penalty(fit, geometry) == 0
