"""Pure sky-geometry science: propagation, frames and observer presets.

This package imports no PostgreSQL, HTTP, CLI or concrete storage module.  It
consumes element sets and instants supplied by a caller and returns numbers.
"""

from leo.sky.frames import (
    EARTH_ROTATION_RATE_RAD_S,
    WGS84_SEMI_MAJOR_AXIS_KM,
    ecef_to_enu_matrix,
    geodetic_to_ecef_km,
    greenwich_mean_sidereal_time_rad,
    julian_day_from_utc_ns,
    look_angles,
    teme_to_ecef,
)
from leo.sky.sites import SITE_PRESETS, SitePreset, preset_names, resolve_preset

__all__ = [
    "EARTH_ROTATION_RATE_RAD_S",
    "SITE_PRESETS",
    "SitePreset",
    "WGS84_SEMI_MAJOR_AXIS_KM",
    "ecef_to_enu_matrix",
    "geodetic_to_ecef_km",
    "greenwich_mean_sidereal_time_rad",
    "julian_day_from_utc_ns",
    "look_angles",
    "preset_names",
    "resolve_preset",
    "teme_to_ecef",
]
