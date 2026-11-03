"""Hardware-covariance oracle for independent low/high receiver-band drift."""

import importlib
import sys
from pathlib import Path

import numpy as np
import pytest


@pytest.fixture
def tool():
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
    try:
        yield importlib.import_module("dsx01_independent_band_drift")
    finally:
        sys.path.pop(0)


def test_independent_bands_have_no_cross_band_or_cross_receiver_covariance(tool):
    groups = np.array([0, 1, 2, 3, 0, 1, 2, 3])
    times = np.array([30.0, 50.0, 70.0, 90.0, 180.0, 210.0, 230.0, 260.0])
    for sigma in (2.0, 10.0):
        columns = tool.independent_band_columns(groups, times, sigma)
        expected = (
            sigma**2
            * (times[:, None] - 150)
            * (times[None, :] - 150)
            * (groups[:, None] == groups[None, :])
        )
        np.testing.assert_allclose(columns @ columns.T, expected)


def test_native_rates_use_hz_per_second_and_shared_band_identity(tool):
    groups, times = np.array([0, 0, 1, 1]), np.array([100.0, 200.0, 100.0, 200.0])
    columns = tool.independent_band_columns(groups, times, 2.0)
    prediction = columns @ np.array([1.5, -0.5, 4.0, 8.0])
    np.testing.assert_allclose(prediction, [-150.0, 150.0, 50.0, -50.0])
