"""Orbit-state port checks independent of archives, RF hardware and storage."""

import numpy as np
import pytest

from leo.analysis.research.track_catalogue_geometry import (
    frequency_grid,
    interpolate_states,
    prepare_geometry,
    prepared_frequency,
)
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


def test_prepared_geometry_matches_original_port_across_sites_and_rf():
    rng = np.random.default_rng(18)
    position = rng.normal(size=(9, 5, 3))
    position *= 7000 / np.linalg.norm(position, axis=2, keepdims=True)
    data = dict(
        time_s=np.arange(5.0), position_km=position, velocity_km_s=rng.normal(size=(9, 5, 3)) * 4
    )
    times = np.array([0.125, 1.25, 2.5, 3.75])
    grid = prepare_geometry(data, times)
    for lat, lon in (
        (37.5, -122.0),
        (35.0, -125.0),
        (40.0, -119.0),
        (89.0, 175.0),
        (-89.0, -175.0),
    ):
        for rf in (11.5e9, np.array([10.7e9, 11.2e9, 12.2e9, 12.7e9])):
            expected = frequency_grid(data, times, lat, lon, rf_hz=rf, altitude_m=100.0)
            actual = prepared_frequency(grid, lat, lon, rf_hz=rf, altitude_m=100.0)
            np.testing.assert_allclose(actual[0], expected[0], atol=1e-6, rtol=1e-12)
            np.testing.assert_allclose(actual[1], expected[1], atol=1e-8, rtol=1e-12)
    with pytest.raises(ValueError):
        grid.position_km[0, 0, 0] = 0
    with pytest.raises(ValueError, match="geodetic"):
        prepared_frequency(grid, 91.0, 0.0)
