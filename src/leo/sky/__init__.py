"""Pure sky-geometry science: propagation, frames, screening and Doppler.

This package imports no PostgreSQL, HTTP, CLI or concrete storage module.  It
consumes element sets and instants supplied by a caller and returns numbers.
:mod:`leo.application.sky_field` is the seam where it meets the archive on disk.

A worked example, from element sets to a predicted Doppler polynomial::

    from leo.contracts.sky import BeamPointingV1, ObserverSiteV1, SkyWindowV1
    from leo.sky import resolve_preset
    from leo.sky.propagation import parse_element_sets, propagate_window
    from leo.sky.screening import observe_window, screen_field

    site = resolve_preset("spinnaker-sausalito")
    observer = ObserverSiteV1(
        latitude_deg=site.latitude_deg,
        longitude_deg=site.longitude_deg,
        altitude_m=site.altitude_m,
        label=site.label,
    )
    pointing = BeamPointingV1(
        boresight_azimuth_deg=180.0, boresight_elevation_deg=45.0, half_angle_deg=3.0
    )
    window = SkyWindowV1(anchor_utc_ns=anchor)

    catalogue = parse_element_sets(snapshot_text)
    propagated = propagate_window(catalogue, window)
    tracks = observe_window(propagated, observer, window)
    objects, selected, excluded = screen_field(
        catalogue, propagated, tracks,
        pointing=pointing, window=window, downlink_frequency_hz=11.7e9,
    )

Results are predictive only.  An object appearing in a report means a published
element set places it in the beam; it is not a claim that anything was received,
detected or identified.
"""

from leo.sky.doppler import (
    SPEED_OF_LIGHT_KM_S,
    doppler_shift_hz,
    evaluate_doppler_polynomial,
    fit_doppler_polynomial,
)
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
from leo.sky.propagation import (
    MINIMUM_PLAUSIBLE_ALTITUDE_KM,
    ElementSetCatalogue,
    ElementSetError,
    PropagatedWindow,
    parse_element_sets,
    propagate_window,
)
from leo.sky.screening import (
    MAXIMUM_REPORTED_OBJECTS,
    ObservedTracks,
    boresight_separation_deg,
    boresight_unit_vector,
    observe_window,
    screen_field,
)
from leo.sky.sites import SITE_PRESETS, SitePreset, preset_names, resolve_preset

__all__ = [
    "EARTH_ROTATION_RATE_RAD_S",
    "MAXIMUM_REPORTED_OBJECTS",
    "MINIMUM_PLAUSIBLE_ALTITUDE_KM",
    "SITE_PRESETS",
    "SPEED_OF_LIGHT_KM_S",
    "ElementSetCatalogue",
    "ElementSetError",
    "ObservedTracks",
    "PropagatedWindow",
    "SitePreset",
    "WGS84_SEMI_MAJOR_AXIS_KM",
    "boresight_separation_deg",
    "boresight_unit_vector",
    "doppler_shift_hz",
    "ecef_to_enu_matrix",
    "evaluate_doppler_polynomial",
    "fit_doppler_polynomial",
    "geodetic_to_ecef_km",
    "greenwich_mean_sidereal_time_rad",
    "julian_day_from_utc_ns",
    "look_angles",
    "observe_window",
    "parse_element_sets",
    "preset_names",
    "propagate_window",
    "resolve_preset",
    "screen_field",
    "teme_to_ecef",
]
