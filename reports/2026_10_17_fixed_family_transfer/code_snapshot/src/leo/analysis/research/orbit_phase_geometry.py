"""Orbit-phase timing perturbations at fixed receiver UTC.

SGP4 states sampled at t+delta are rotated back to the Earth orientation at t.
This separates an orbital phase hypothesis from a receiver UTC-clock shift.
No orbit correction is estimated here, and interpolation never extrapolates.
"""

import numpy as np

from leo.analysis.research.track_catalogue_geometry import interpolate_states
from leo.sky.frames import ecef_to_enu_matrix, geodetic_to_ecef_km, look_angles

EARTH_ROTATION_RAD_S = 7.29211514670698e-5


def phase_shifted_states(bank, time_s, phase_seconds):
    phases = np.asarray(phase_seconds, float)
    times = np.asarray(time_s, float)
    count = np.asarray(bank["position_km"]).shape[0]
    if phases.ndim == 0:
        phases = np.full(count, float(phases))
    if phases.shape != (count,) or not np.isfinite(phases).all():
        raise ValueError("finite scalar or one orbit phase per satellite required")
    # The common interpolator supplies geometry validation even for an empty
    # request. Per-satellite phases then use the same linear interpolation rule.
    interpolate_states(bank, np.array([], float))
    if times.ndim != 1 or not np.isfinite(times).all():
        raise ValueError("finite one-dimensional observation times required")
    knots = np.asarray(bank["time_s"], float)
    requested = times[None, :] + phases[:, None]
    if np.any(requested < knots[0]) or np.any(requested > knots[-1]):
        raise ValueError("orbit phase interpolation never extrapolates")
    index = np.clip(np.searchsorted(knots, requested, side="right") - 1, 0, len(knots) - 2)
    fraction = (requested - knots[index]) / (knots[index + 1] - knots[index])
    rows = np.arange(count)[:, None]
    states = []
    angle = EARTH_ROTATION_RAD_S * phases
    cosine, sine = np.cos(angle)[:, None], np.sin(angle)[:, None]
    for name in ("position_km", "velocity_km_s"):
        source = np.asarray(bank[name], float)
        values = source[rows, index] + fraction[:, :, None] * (
            source[rows, index + 1] - source[rows, index]
        )
        x, y = values[:, :, 0].copy(), values[:, :, 1].copy()
        values[:, :, 0] = cosine * x - sine * y
        values[:, :, 1] = sine * x + cosine * y
        states.append(values)
    return tuple(states)


def phase_frequency_grid(
    bank, time_s, latitude_deg, longitude_deg, *, phase_seconds=0.0, altitude_m=0.0, rf_hz=11.5e9
):
    if not (-90 <= latitude_deg <= 90 and -180 <= longitude_deg <= 180):
        raise ValueError("geodetic coordinate outside domain")
    if not np.isfinite(altitude_m) or not np.isfinite(rf_hz) or rf_hz <= 0:
        raise ValueError("finite height and positive reference RF required")
    position, velocity = phase_shifted_states(bank, time_s, phase_seconds)
    observer = geodetic_to_ecef_km(latitude_deg, longitude_deg, altitude_m)
    rotation = ecef_to_enu_matrix(latitude_deg, longitude_deg)
    _, elevation, _, rate = look_angles(position, velocity, observer, rotation)
    return -rf_hz * rate / 299792.458, elevation
