"""Prepared phase derivatives agree with direct nonlinear orbit geometry."""

import numpy as np
import pytest

from leo.analysis.research.orbit_phase_geometry import phase_frequency_grid
from leo.analysis.research.phase_linear_geometry import (
    phase_linear_frequency,
    prepare_phase_geometry,
)


@pytest.mark.parametrize("phases", [0.0, np.array([0.2, -0.1])])
def test_cached_frequency_and_sensitivity_match_nonlinear_geometry(phases):
    times = np.arange(-5.0, 16)
    position = np.stack([7000 + 0 * times, 7 * times, 200 + 0 * times], axis=1)
    velocity = np.broadcast_to([0, 7, 0], position.shape).copy()
    bank = dict(
        time_s=times,
        position_km=np.stack([position, position + [100, 0, 100]]),
        velocity_km_s=np.stack([velocity, velocity]),
    )
    sample = np.array([0.4, 4.4, 10.4])
    prepared = prepare_phase_geometry(bank, sample, phases)
    frequency, elevation, derivative = phase_linear_frequency(prepared, 37.5, -122)
    exact, angle = phase_frequency_grid(bank, sample, 37.5, -122, phase_seconds=phases)
    np.testing.assert_allclose(frequency, exact, atol=1e-8)
    np.testing.assert_allclose(elevation, angle, atol=1e-8)
    plus, _ = phase_frequency_grid(bank, sample, 37.5, -122, phase_seconds=phases + 0.05)
    minus, _ = phase_frequency_grid(bank, sample, 37.5, -122, phase_seconds=phases - 0.05)
    np.testing.assert_allclose(derivative, (plus - minus) / 0.1, rtol=1e-6, atol=1e-3)
    assert not prepared.position_derivative.flags.writeable
