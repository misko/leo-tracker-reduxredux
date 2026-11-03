"""A satellite phase change must not silently rotate the observing Earth."""

import numpy as np
import pytest

from leo.analysis.research.orbit_phase_geometry import (
    EARTH_ROTATION_RAD_S,
    phase_frequency_grid,
    phase_shifted_states,
)
from leo.analysis.research.track_catalogue_geometry import frequency_grid


def bank():
    t = np.arange(-10.0, 21)
    p = np.stack([7000 + 0 * t, 7 * t, 100 + 0 * t], axis=1)
    v = np.broadcast_to([0, 7, 0], p.shape).copy()
    return dict(
        time_s=t, position_km=np.stack([p, p + [0, 0, 100]]), velocity_km_s=np.stack([v, v])
    )


def test_zero_phase_nests_original_frequency_exactly():
    sky = bank()
    t = np.array([0.25, 3.75, 10.0])
    a = frequency_grid(sky, t, 37.5, -122)
    b = phase_frequency_grid(sky, t, 37.5, -122, phase_seconds=np.zeros(2))
    for expected, actual in zip(a, b, strict=True):
        np.testing.assert_allclose(actual, expected, atol=1e-9)


def test_satellite_specific_phase_is_rotated_to_observation_utc():
    t = np.arange(-10.0, 21)
    # Independent circular inertial orbit: ECEF angular rate is n - omega.
    inertial_rate = 0.0011
    ecef_rate = inertial_rate - EARTH_ROTATION_RAD_S
    base = np.stack([7000 * np.cos(ecef_rate * t), 7000 * np.sin(ecef_rate * t), 0 * t], axis=1)
    speed = np.stack([-ecef_rate * base[:, 1], ecef_rate * base[:, 0], 0 * t], axis=1)
    sky = dict(time_s=t, position_km=np.stack([base, base]), velocity_km_s=np.stack([speed, speed]))
    phases = np.array([2.0, -3.0])
    p, v = phase_shifted_states(sky, [0.0], phases)
    for i, delta in enumerate(phases):
        theta = inertial_rate * delta
        expected = 7000 * np.array([np.cos(theta), np.sin(theta), 0])
        np.testing.assert_allclose(p[i, 0], expected, atol=1e-10)
        np.testing.assert_allclose(
            v[i, 0], ecef_rate * np.array([-expected[1], expected[0], 0]), atol=1e-10
        )
        # This correction is hundreds of meters per second of phase shift.
        uncorrected_utc_shift = 7000 * np.array(
            [np.cos(ecef_rate * delta), np.sin(ecef_rate * delta), 0]
        )
        assert np.linalg.norm(p[i, 0] - uncorrected_utc_shift) > 0.5


def test_phase_cannot_extrapolate_or_accept_bad_shapes():
    with pytest.raises(ValueError, match="never extrapolates"):
        phase_shifted_states(bank(), [20], 2)
    with pytest.raises(ValueError):
        phase_shifted_states(bank(), [0], [0, 0, 0])
