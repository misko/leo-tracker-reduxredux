"""Checks for the standalone sensitivity experiment; no hardware required."""
import numpy as np
from simulate import (
    FC, satellite, state, frequency, geometry, profile_delay, fit_residual,
)


def test_doppler_matches_numerical_range_derivative():
    sat = satellite()
    obs, center, *_ = geometry(sat, 3.)
    t = center + np.array([-100., 40., 100.])
    dt = .05
    rp, _ = state(sat, t+dt)
    rm, _ = state(sat, t-dt)
    derivative = (np.linalg.norm(rp-obs, axis=1)-np.linalg.norm(rm-obs, axis=1))/(2*dt)
    # SGP4 analytic velocities include small approximations relative to differencing.
    np.testing.assert_allclose(frequency(sat, t, obs), -FC/299792.458*derivative,
                               rtol=2e-4, atol=.5)


def test_known_time_shift_is_recovered():
    sat = satellite()
    obs, center, *_ = geometry(sat, 3.)
    t = center+np.linspace(-10, 10, 121)
    y = frequency(sat, t+.37, obs)+1234.
    delay, fit = profile_delay(sat, t, y, obs, 0)
    assert abs(delay-.37) < 1e-5
    assert fit[0] < .001


def test_small_element_response_scales_and_reverses():
    sat = satellite()
    obs, center, *_ = geometry(sat, 3.)
    t = center+np.linspace(-10, 10, 121)
    base = frequency(sat, t, obs)
    delta = np.deg2rad(.001)
    plus = frequency(satellite('mo', delta), t, obs)-base
    minus = frequency(satellite('mo', -delta), t, obs)-base
    half = frequency(satellite('mo', delta/2), t, obs)-base
    np.testing.assert_allclose(plus, -minus, rtol=.001, atol=.001)
    np.testing.assert_allclose(plus, 2*half, rtol=.001, atol=.001)


def test_nested_fits_and_zero_control():
    u = np.linspace(-10, 10, 121)
    y = 21+3*u+.4*u*u
    fits = [fit_residual(u, y, d)[0] for d in range(3)]
    assert fits[0] > fits[1] > fits[2]
    assert fits[2] < 1e-10
    assert fit_residual(u, np.zeros_like(u), 2)[0] == 0
