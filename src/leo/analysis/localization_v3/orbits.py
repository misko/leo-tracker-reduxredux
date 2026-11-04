"""Pure regional orbit-bank construction with explicitly supplied coordinates.

The application must supply its causal catalogue through the archive port.
This component has no archive, evaluation-site or historical-result access.
"""
import numpy as np

from leo.sky.frames import (
    ecef_to_enu_matrix,
    geodetic_to_ecef_km,
    greenwich_mean_sidereal_time_rad,
    julian_day_from_utc_ns,
    look_angles,
    teme_to_ecef,
)
from leo.sky.propagation import ElementSetCatalogue, propagate_grid
from leo.sky.sampling import SamplingGrid


def ecef_states(catalogue, origin_utc_ns, times):
    """Preserve the original SGP4/time-rounding/Earth-rotation operation order."""
    utc = origin_utc_ns + np.rint(times * 1e9).astype(np.int64)
    state = propagate_grid(catalogue, SamplingGrid(tuple(map(int, utc)), 0, 1.0))
    jd, fr = julian_day_from_utc_ns(utc)
    position, velocity = teme_to_ecef(
        state.position_teme_km, state.velocity_teme_km_s,
        greenwich_mean_sidereal_time_rad(jd, fr))
    return position, velocity, state.usable


def regional_bank(catalogue, origin_utc_ns, duration_s, *,
                  screen_latitude_deg, screen_longitude_deg):
    """Broad regional screening, retaining source indices for causal provenance.

    The explicit screening centre is distinct from the position-search centre.
    Historical defaults belong in application configuration, never this kernel.
    """
    if not np.isfinite(duration_s) or duration_s < 0:
        raise ValueError('Finite nonnegative recording duration required')
    duration = max(300., duration_s)
    grid = np.arange(-17., np.ceil(duration) + 18)
    coarse = np.arange(0., duration + 5, 5.)
    p, v, good = ecef_states(catalogue, origin_utc_ns, coarse)
    _, elevation, _, _ = look_angles(
        p, v, geodetic_to_ecef_km(screen_latitude_deg, screen_longitude_deg, 0.),
        ecef_to_enu_matrix(screen_latitude_deg, screen_longitude_deg))
    selected = np.flatnonzero(good & (elevation.max(axis=1) >= -12))
    if not len(selected):
        raise ValueError('no regional causal candidates')
    chosen = ElementSetCatalogue(tuple(catalogue.names[i] for i in selected),
                                 tuple(catalogue.satellite_numbers[i] for i in selected),
                                 tuple(catalogue.satellites[i] for i in selected))
    p, v, good = ecef_states(chosen, origin_utc_ns, grid)
    if not good.all():
        raise ValueError('causal state bank propagation failed')
    return dict(catalogue=chosen, source_indices=selected,
                bank=dict(time_s=grid, position_km=p, velocity_km_s=v,
                          norad=np.array(chosen.satellite_numbers),
                          phase_sigma_s=np.ones(len(chosen))))
