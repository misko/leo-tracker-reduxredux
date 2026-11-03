"""Analytic one-way links and frame-rotation controls for receive-time Doppler."""

import importlib
import sys
from pathlib import Path

import numpy as np
import pytest


@pytest.fixture
def tool():
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
    try:
        yield importlib.import_module("dsx01_reception_doppler")
    finally:
        sys.path.pop(0)


def test_radial_constant_velocity_matches_exact_coordinate_frequency_and_delay(tool):
    velocity, initial = 7.0, 800.0
    times = np.array([0.0, 3.0, 12.0])

    def states(t):
        return np.column_stack((initial + velocity * t, np.zeros((len(t), 2)))), np.tile(
            [velocity, 0.0, 0.0], (len(t), 1)
        )

    f, delay = tool.reception_frequency(states, times, np.zeros(3), omega=0)
    np.testing.assert_allclose(
        delay, (initial + velocity * times) / (tool.C_KM_S + velocity), rtol=1e-13
    )
    np.testing.assert_allclose(f, -11.5e9 * velocity / (tool.C_KM_S + velocity), rtol=1e-13)


def test_radial_special_relativity_matches_longitudinal_doppler(tool):
    velocity = 7.0

    def states(t):
        return np.column_stack((800 + velocity * t, np.zeros((len(t), 2)))), np.tile(
            [velocity, 0.0, 0.0], (len(t), 1)
        )

    f, _ = tool.reception_frequency(
        states, np.array([0.0, 3.0]), np.zeros(3), omega=0, relativistic=True, earth_potential=False
    )
    beta = velocity / tool.C_KM_S
    expected = 11.5e9 * np.expm1(0.5 * (np.log1p(-beta) - np.log1p(beta)))
    np.testing.assert_allclose(f, expected, rtol=1e-13)


def test_corotating_fixed_ecef_link_has_zero_coordinate_doppler(tool):
    def states(t):
        return np.tile([40000.0, 12000.0, 3000.0], (len(t), 1)), np.zeros((len(t), 3))

    f, delay = tool.reception_frequency(
        states, np.array([0.0, 100.0]), np.array([6300.0, 100.0, 100.0])
    )
    np.testing.assert_allclose(f, 0, atol=1e-10)
    assert (delay > 0).all()


def test_rotate_z_matches_right_handed_quarter_turn(tool):
    np.testing.assert_allclose(
        tool.rotate_z([[1.0, 0.0, 2.0]], np.pi / 2), [[0.0, 1.0, 2.0]], atol=1e-15
    )
