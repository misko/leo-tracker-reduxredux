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
    grid = coarse_grid(window, pointing)
    tracks = observe_grid(propagate_grid(catalogue, grid), observer, grid)
    classification = classify_coarse(tracks, pointing, grid)

Objects in ``classification.ambiguous`` need a second look on
``refinement_grid(window)`` before their membership is decided;
:class:`leo.application.sky_field.SkyFieldService` performs both passes.

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
    element_line_checksum,
    parse_element_sets,
    propagate_grid,
    propagate_window,
)
from leo.sky.sampling import (
    MAX_ANGULAR_RATE_DEG_S,
    REFINEMENT_ANGULAR_TOLERANCE_DEG,
    SamplingGrid,
    candidate_margin_deg,
    coarse_grid,
    presentation_grid,
    refinement_grid,
)
from leo.sky.screening import (
    MAXIMUM_REPORTED_OBJECTS,
    CoarseClassification,
    ObservedTracks,
    boresight_separation_deg,
    boresight_unit_vector,
    build_predictions,
    classify_coarse,
    eligible_at_each_sample,
    observe_grid,
    summarise_exclusions,
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
    "CoarseClassification",
    "MAX_ANGULAR_RATE_DEG_S",
    "ObservedTracks",
    "REFINEMENT_ANGULAR_TOLERANCE_DEG",
    "SamplingGrid",
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
    "build_predictions",
    "candidate_margin_deg",
    "classify_coarse",
    "coarse_grid",
    "element_line_checksum",
    "eligible_at_each_sample",
    "observe_grid",
    "presentation_grid",
    "propagate_grid",
    "refinement_grid",
    "summarise_exclusions",
    "parse_element_sets",
    "preset_names",
    "propagate_window",
    "resolve_preset",
    "teme_to_ecef",
]
