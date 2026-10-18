"""Prepared orbit-phase tangent geometry with original observation support."""

from dataclasses import dataclass

import numpy as np

from leo.analysis.research.orbit_phase_geometry import phase_shifted_states
from leo.analysis.research.track_catalogue_geometry import PreparedGeometry
from leo.sky.frames import ecef_to_enu_matrix, geodetic_to_ecef_km


@dataclass(frozen=True)
class PreparedPhaseGeometry:
    geometry: PreparedGeometry
    position_derivative: np.ndarray
    velocity_derivative: np.ndarray
    numerator_derivative: np.ndarray
    position_dot_derivative: np.ndarray


def prepare_phase_geometry(bank, times, phases=0.0, *, derivative_step_s=0.05):
    if not np.isfinite(derivative_step_s) or derivative_step_s <= 0:
        raise ValueError("positive finite phase difference step required")
    phases = np.asarray(phases)
    position, velocity = phase_shifted_states(bank, times, phases)
    plus_p, plus_v = phase_shifted_states(bank, times, phases + derivative_step_s)
    minus_p, minus_v = phase_shifted_states(bank, times, phases - derivative_step_s)
    dp = (plus_p - minus_p) / (2 * derivative_step_s)
    dv = (plus_v - minus_v) / (2 * derivative_step_s)
    norm = np.einsum("snj,snj->sn", position, position)
    pv = np.einsum("snj,snj->sn", position, velocity)
    numerator = np.einsum("snj,snj->sn", dp, velocity) + np.einsum("snj,snj->sn", position, dv)
    pw = np.einsum("snj,snj->sn", position, dp)
    for array in (position, velocity, norm, pv, dp, dv, numerator, pw):
        array.setflags(write=False)
    return PreparedPhaseGeometry(
        PreparedGeometry(position, velocity, norm, pv), dp, dv, numerator, pw
    )


def phase_linear_frequency(grid, latitude_deg, longitude_deg, *, altitude_m=0.0, rf_hz=11.5e9):
    if not (-90 <= latitude_deg <= 90 and -180 <= longitude_deg <= 180):
        raise ValueError("geodetic coordinate outside domain")
    if not np.isfinite(altitude_m) or not np.isfinite(rf_hz) or rf_hz <= 0:
        raise ValueError("finite height and positive reference RF required")
    observer = geodetic_to_ecef_km(latitude_deg, longitude_deg, altitude_m)
    up = ecef_to_enu_matrix(latitude_deg, longitude_deg)[2]
    base = grid.geometry
    distance = np.sqrt(
        base.position_norm_squared
        - 2 * np.einsum("snj,j->sn", base.position_km, observer)
        + observer @ observer
    )
    if np.any(distance <= 0) or not np.isfinite(distance).all():
        raise ValueError("positive finite satellite ranges required")
    numerator = base.position_dot_velocity - np.einsum("snj,j->sn", base.velocity_km_s, observer)
    numerator_derivative = grid.numerator_derivative - np.einsum(
        "snj,j->sn", grid.velocity_derivative, observer
    )
    range_derivative = grid.position_dot_derivative - np.einsum(
        "snj,j->sn", grid.position_derivative, observer
    )
    rate = numerator / distance
    derivative = numerator_derivative / distance - numerator * range_derivative / distance**3
    vertical = np.einsum("snj,j->sn", base.position_km, up) - observer @ up
    elevation = np.rad2deg(np.arcsin(np.clip(vertical / distance, -1, 1)))
    return -rf_hz * rate / 299792.458, elevation, -rf_hz * derivative / 299792.458
