"""Independent-design oracle for radio-only affine hardware information."""

import importlib
import sys
from pathlib import Path

import numpy as np
import pytest


@pytest.fixture
def tool():
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
    try:
        yield importlib.import_module("probe_dsx01_radio_drift_information")
    finally:
        sys.path.pop(0)


def test_two_frequencies_agree_with_closed_form_differential_slope_information(tool):
    t = np.linspace(-100, 100, 31)
    hardware = np.tile(np.column_stack((np.ones(len(t)), t)), (2, 1))
    q = np.repeat([0.95, 1.05], len(t))
    times = np.tile(t, 2)
    family = q[:, None] * np.column_stack((np.ones(len(times)), times, times**2))
    y, a, _ = tool.remove_family(np.zeros(len(times)), hardware, family)
    result = tool.information(a, y, {"rate": [0, 1]})["target_information"]["rate"]
    expected_variance = (1 / 0.95**2 + 1 / 1.05**2) / ((1 / 0.95 - 1 / 1.05) ** 2 * np.sum(t**2))
    assert result["identifiable"]
    np.testing.assert_allclose(result["nominal_sigma"] ** 2, expected_variance, rtol=1e-12)


def test_one_frequency_cannot_identify_hardware_slope_against_free_source_polynomial(tool):
    t = np.linspace(-100, 100, 31)
    hardware = np.column_stack((np.ones(len(t)), t))
    family = np.column_stack((np.ones(len(t)), t, t**2))
    y, a, _ = tool.remove_family(np.zeros(len(t)), hardware, family)
    result = tool.information(a, y, {"rate": [0, 1]})["target_information"]["rate"]
    assert not result["identifiable"] and result["nominal_sigma"] is None
