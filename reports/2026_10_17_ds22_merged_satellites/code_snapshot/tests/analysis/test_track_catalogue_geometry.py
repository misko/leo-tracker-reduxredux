"""Orbit-state port checks independent of archives, RF hardware and storage."""

import numpy as np
import pytest

from leo.analysis.research.track_catalogue_geometry import frequency_grid, interpolate_states
from leo.sky.frames import ecef_to_enu_matrix, geodetic_to_ecef_km


def bank():
    site = geodetic_to_ecef_km(37.5, -122.0, 0.0)
    up = ecef_to_enu_matrix(37.5, -122.0)[2]
    t = np.arange(3.0)
    return dict(
        time_s=t,
        position_km=(site[None, :] + (550 + t[:, None]) * up)[None, :, :],
        velocity_km_s=np.broadcast_to(up, (1, 3, 3)).copy(),
    )


def test_doppler_sign_units_carrier_scaling_and_zenith():
    frequency, elevation = frequency_grid(
        bank(), np.array([0.5, 1.5]), 37.5, -122.0, rf_hz=np.array([10e9, 12e9])
    )
    np.testing.assert_allclose(frequency, -np.array([[10e9, 12e9]]) / 299792.458, atol=1e-8)
    np.testing.assert_allclose(elevation, 90.0, atol=1e-6)


def test_exact_knots_endpoints_and_input_immutability():
    data = bank()
    old = data["position_km"].copy()
    p, v = interpolate_states(data, np.array([0.0, 1.0, 2.0]))
    np.testing.assert_array_equal(p, old)
    p[0, 0, 0] += 1000
    np.testing.assert_array_equal(data["position_km"], old)
    assert np.isfinite(v).all()


def test_no_extrapolation_or_invalid_state_masking():
    with pytest.raises(ValueError, match="extrapolates"):
        interpolate_states(bank(), np.array([-0.1]))
    data = bank()
    data["position_km"][0, 0, 0] = np.nan
    with pytest.raises(ValueError, match="finite satellite"):
        interpolate_states(data, np.array([0.5]))
    with pytest.raises(ValueError, match="geodetic"):
        frequency_grid(bank(), np.array([0.5]), 95.0, 0.0)
