"""Report-local geometry for turning dual-LNB phase into sky constraints."""
from __future__ import annotations

import numpy as np

C_M_PER_S = 299_792_458.0
TAU = 2 * np.pi


def wrap_radians(value):
    return (np.asarray(value, float) + np.pi) % TAU - np.pi


def horizontal_axis_enu(azimuth_deg: float = 79.0) -> np.ndarray:
    """ENU unit vector for azimuth measured clockwise from north."""
    azimuth = np.radians(azimuth_deg)
    return np.array([np.sin(azimuth), np.cos(azimuth), 0.0])


def sky_direction_enu(azimuth_deg, elevation_deg) -> np.ndarray:
    """Unit line of sight from the receiver toward the satellite."""
    azimuth = np.radians(np.asarray(azimuth_deg, float))
    elevation = np.radians(np.asarray(elevation_deg, float))
    azimuth, elevation = np.broadcast_arrays(azimuth, elevation)
    return np.stack((np.cos(elevation) * np.sin(azimuth),
                     np.cos(elevation) * np.cos(azimuth),
                     np.sin(elevation)), axis=-1)


def incidence_projection(azimuth_deg, elevation_deg, baseline_azimuth_deg=79.0):
    """Return b_hat dot s = cos(el) cos(az-baseline_az)."""
    return np.sum(sky_direction_enu(azimuth_deg, elevation_deg) *
                  horizontal_axis_enu(baseline_azimuth_deg), axis=-1)


def geometric_phase_rad(azimuth_deg, elevation_deg, baseline_length_m,
                        rf_hz, baseline_azimuth_deg=79.0,
                        instrumental_phase_rad=0.0):
    """Wrapped RX1-minus-RX0 phase for the far-field convention in the report."""
    path_projection = float(baseline_length_m) * incidence_projection(
        azimuth_deg, elevation_deg, baseline_azimuth_deg)
    return wrap_radians(TAU * np.asarray(rf_hz, float) * path_projection / C_M_PER_S
                        + np.asarray(instrumental_phase_rad, float))


def path_length_hypotheses(phase_rad, rf_hz, instrumental_phase_rad=0.0,
                           minimum_m=-np.inf, maximum_m=np.inf):
    """Enumerate path projections consistent with wrapped phase in an interval."""
    frequency = float(rf_hz)
    if not np.isfinite(frequency) or frequency <= 1e9:
        raise ValueError("physical RF above 1 GHz is required")
    if minimum_m > maximum_m:
        raise ValueError("invalid path interval")
    wavelength = C_M_PER_S / frequency
    fractional = float(wrap_radians(float(phase_rad) - float(instrumental_phase_rad)) / TAU)
    first = int(np.ceil(minimum_m / wavelength - fractional))
    last = int(np.floor(maximum_m / wavelength - fractional))
    aliases = np.arange(first, last + 1, dtype=int)
    return aliases, wavelength * (aliases + fractional)


def projection_hypotheses(phase_rad, rf_hz, baseline_length_m,
                          instrumental_phase_rad=0.0):
    """Return all physically allowed b_hat dot s aliases for a known baseline."""
    length = abs(float(baseline_length_m))
    if not np.isfinite(length) or length <= 0:
        raise ValueError("nonzero finite baseline length is required")
    aliases, paths = path_length_hypotheses(
        phase_rad, rf_hz, instrumental_phase_rad, -length, length)
    projection = paths / float(baseline_length_m)
    valid = abs(projection) <= 1 + 1e-12
    return aliases[valid], np.clip(projection[valid], -1, 1)


def sky_constraint(projection, azimuth_deg, baseline_azimuth_deg=79.0):
    """Elevation on the visible hemisphere for a baseline-projection alias.

    NaN means that azimuth cannot produce the requested projection.
    """
    value = float(projection)
    azimuth = np.asarray(azimuth_deg, float)
    denominator = np.cos(np.radians(azimuth - baseline_azimuth_deg))
    ratio = np.divide(value, denominator, out=np.full_like(denominator, np.nan),
                      where=abs(denominator) > 1e-12)
    valid = (ratio >= 0) & (ratio <= 1)
    return np.where(valid, np.degrees(np.arccos(np.clip(ratio, 0, 1))), np.nan)


def simultaneous_phase_difference(azimuth_a_deg, elevation_a_deg, rf_a_hz,
                                  azimuth_b_deg, elevation_b_deg, rf_b_hz,
                                  baseline_length_m,
                                  baseline_azimuth_deg=79.0,
                                  differential_delay_s=0.0):
    """Wrapped phase(B)-phase(A), with common instrumental phase cancelled."""
    pa = incidence_projection(azimuth_a_deg, elevation_a_deg, baseline_azimuth_deg)
    pb = incidence_projection(azimuth_b_deg, elevation_b_deg, baseline_azimuth_deg)
    cycles = float(baseline_length_m) * (np.asarray(rf_b_hz) * pb -
                                         np.asarray(rf_a_hz) * pa) / C_M_PER_S
    # A differential path delay is frequency dependent and does not cancel if
    # the two signals have different physical RF carriers.
    cycles += (np.asarray(rf_b_hz) - np.asarray(rf_a_hz)) * differential_delay_s
    return wrap_radians(TAU * cycles)


def phase_degrees_to_path_mm(phase_error_deg, rf_hz):
    """Local unwrapped path sensitivity; not an ambiguity resolver."""
    return 1e3 * (C_M_PER_S / np.asarray(rf_hz, float)) * np.asarray(phase_error_deg) / 360.0
