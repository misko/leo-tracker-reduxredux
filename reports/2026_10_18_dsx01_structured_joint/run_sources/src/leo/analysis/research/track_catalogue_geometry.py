"""Pure sampled-orbit port for component-level Doppler matching and site fits."""

from dataclasses import dataclass

import numpy as np

from leo.sky.frames import ecef_to_enu_matrix, geodetic_to_ecef_km, look_angles


@dataclass(frozen=True)
class PreparedGeometry:
    position_km: np.ndarray
    velocity_km_s: np.ndarray
    position_norm_squared: np.ndarray
    position_dot_velocity: np.ndarray


def interpolate_states(bank, time_s):
    times = np.asarray(bank["time_s"], float)
    requested = np.asarray(time_s, float)
    position = np.asarray(bank["position_km"], float)
    velocity = np.asarray(bank["velocity_km_s"], float)
    if (
        times.ndim != 1
        or len(times) < 2
        or np.any(np.diff(times) <= 0)
        or not np.isfinite(times).all()
        or requested.ndim != 1
        or not np.isfinite(requested).all()
    ):
        raise ValueError("finite ordered bank and one-dimensional request required")
    if (
        position.shape != velocity.shape
        or position.ndim != 3
        or position.shape[1:] != (len(times), 3)
    ):
        raise ValueError("satellite/time/XYZ state arrays required")
    if not np.isfinite(position).all() or not np.isfinite(velocity).all():
        raise ValueError("finite satellite states required")
    if np.any(requested < times[0]) or np.any(requested > times[-1]):
        raise ValueError("orbit interpolation never extrapolates")
    index = np.clip(np.searchsorted(times, requested, side="right") - 1, 0, len(times) - 2)
    fraction = (requested - times[index]) / (times[index + 1] - times[index])
    p = position[:, index] + fraction[None, :, None] * (position[:, index + 1] - position[:, index])
    v = velocity[:, index] + fraction[None, :, None] * (velocity[:, index + 1] - velocity[:, index])
    return p, v


def frequency_grid(bank, time_s, latitude_deg, longitude_deg, *, altitude_m=0.0, rf_hz=11.5e9):
    if not (-90 <= latitude_deg <= 90 and -180 <= longitude_deg <= 180):
        raise ValueError("geodetic coordinate outside domain")
    if (
        not np.isfinite(altitude_m)
        or not np.all(np.isfinite(rf_hz))
        or np.any(np.asarray(rf_hz) <= 0)
    ):
        raise ValueError("finite height and positive finite carrier required")
    position, velocity = interpolate_states(bank, time_s)
    observer = geodetic_to_ecef_km(latitude_deg, longitude_deg, altitude_m)
    enu = ecef_to_enu_matrix(latitude_deg, longitude_deg)
    _, elevation, _, rate = look_angles(position, velocity, observer, enu)
    return -np.asarray(rf_hz) * rate / 299792.458, elevation


def prepare_geometry(bank, time_s):
    """Interpolate once; retain immutable site-independent contractions."""
    position, velocity = interpolate_states(bank, time_s)
    norm = np.einsum("snj,snj->sn", position, position)
    product = np.einsum("snj,snj->sn", position, velocity)
    for values in (position, velocity, norm, product):
        values.setflags(write=False)
    return PreparedGeometry(position, velocity, norm, product)


def prepared_frequency(grid, latitude_deg, longitude_deg, *, altitude_m=0.0, rf_hz=11.5e9):
    """Same radial-velocity geometry without repeated 3-D temporary arrays."""
    if not (-90 <= latitude_deg <= 90 and -180 <= longitude_deg <= 180):
        raise ValueError("geodetic coordinate outside domain")
    if (
        not np.isfinite(altitude_m)
        or not np.isfinite(rf_hz).all()
        or np.any(np.asarray(rf_hz) <= 0)
    ):
        raise ValueError("finite height and positive finite carrier required")
    observer = geodetic_to_ecef_km(latitude_deg, longitude_deg, altitude_m)
    up = ecef_to_enu_matrix(latitude_deg, longitude_deg)[2]
    dot = np.einsum("snj,j->sn", grid.position_km, observer)
    range_squared = grid.position_norm_squared - 2 * dot + observer @ observer
    if np.any(range_squared <= 0) or not np.isfinite(range_squared).all():
        raise ValueError("positive finite satellite ranges required")
    distance = np.sqrt(range_squared)
    rate = (
        grid.position_dot_velocity - np.einsum("snj,j->sn", grid.velocity_km_s, observer)
    ) / distance
    vertical = np.einsum("snj,j->sn", grid.position_km, up) - observer @ up
    elevation = np.rad2deg(np.arcsin(np.clip(vertical / distance, -1.0, 1.0)))
    return -np.asarray(rf_hz) * rate / 299792.458, elevation
