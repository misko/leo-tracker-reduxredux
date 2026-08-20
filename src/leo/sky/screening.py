"""Select the catalogued objects that fall inside one antenna beam.

The selection is deliberately conservative and always accounts for what it drops.
An object leaves the report for exactly one of four reasons -- propagation
failure, an implausible element set, the horizon mask, or the beam cone -- and
every reason is counted so that "nothing in the beam" can be distinguished from
"nothing was considered".
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from leo.contracts.sky import (
    BeamPointingV1,
    DopplerPolynomialV1,
    ObserverSiteV1,
    SkyExclusionsV1,
    SkyObjectPredictionV1,
    SkyWindowV1,
)
from leo.sky.doppler import doppler_shift_hz, fit_doppler_polynomial
from leo.sky.frames import (
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
    PropagatedWindow,
)

MAXIMUM_REPORTED_OBJECTS = 512

# The cone boundary is inclusive, and an object placed exactly on it must be
# selected deterministically rather than by whichever way the last rounding went.
# One nanodegree is far below any physically meaningful pointing accuracy.
_BEAM_EDGE_TOLERANCE_DEG = 1e-9


@dataclass(frozen=True, slots=True)
class ObservedTracks:
    """Horizon-frame tracks for every catalogued object across one window.

    Every array is shaped ``(objects, knots)`` except ``anchor_index``, which
    identifies the knot that sits exactly on the window anchor.
    """

    azimuth_deg: NDArray[np.float64]
    elevation_deg: NDArray[np.float64]
    range_km: NDArray[np.float64]
    range_rate_km_s: NDArray[np.float64]
    altitude_km: NDArray[np.float64]
    usable: NDArray[np.bool_]
    anchor_index: int


def observe_window(
    propagated: PropagatedWindow, observer: ObserverSiteV1, window: SkyWindowV1
) -> ObservedTracks:
    """Convert a propagated window into observer-relative tracks."""

    knots = np.asarray(propagated.utc_ns, dtype=np.int64)
    julian_day, fraction = julian_day_from_utc_ns(knots)
    gmst = greenwich_mean_sidereal_time_rad(julian_day, fraction)
    position, velocity = teme_to_ecef(
        propagated.position_teme_km, propagated.velocity_teme_km_s, gmst[None, :]
    )
    observer_ecef = geodetic_to_ecef_km(
        observer.latitude_deg, observer.longitude_deg, observer.altitude_m
    )
    enu = ecef_to_enu_matrix(observer.latitude_deg, observer.longitude_deg)
    azimuth, elevation, slant, rate = look_angles(position, velocity, observer_ecef, enu)
    altitude = np.linalg.norm(position, axis=-1) - WGS84_SEMI_MAJOR_AXIS_KM
    try:
        anchor_index = propagated.utc_ns.index(window.anchor_utc_ns)
    except ValueError as error:  # pragma: no cover - guarded by SkyWindowV1
        raise ValueError("propagated window does not contain its anchor instant") from error
    return ObservedTracks(
        azimuth_deg=azimuth,
        elevation_deg=elevation,
        range_km=slant,
        range_rate_km_s=rate,
        altitude_km=altitude,
        usable=propagated.usable,
        anchor_index=anchor_index,
    )


def boresight_unit_vector(pointing: BeamPointingV1) -> NDArray[np.float64]:
    """Return the boresight direction as an east/north/up unit vector."""

    azimuth = np.deg2rad(pointing.boresight_azimuth_deg)
    elevation = np.deg2rad(pointing.boresight_elevation_deg)
    return np.array(
        [
            np.cos(elevation) * np.sin(azimuth),
            np.cos(elevation) * np.cos(azimuth),
            np.sin(elevation),
        ],
        dtype=np.float64,
    )


def boresight_separation_deg(
    azimuth_deg: NDArray[np.float64],
    elevation_deg: NDArray[np.float64],
    pointing: BeamPointingV1,
) -> NDArray[np.float64]:
    """Angular separation from boresight, in degrees.

    Computed as the angle between unit vectors rather than by combining azimuth
    and elevation differences, so it stays correct near the zenith and across
    the north wrap, where a naive difference is badly wrong.

    The angle comes from ``arctan2`` of the cross-product magnitude against the
    dot product rather than from ``arccos`` of the dot product alone.  ``arccos``
    has unbounded derivative at zero separation, so an object exactly on
    boresight would otherwise report a separation near 1e-6 deg instead of zero.
    """

    azimuth = np.deg2rad(np.asarray(azimuth_deg, dtype=np.float64))
    elevation = np.deg2rad(np.asarray(elevation_deg, dtype=np.float64))
    direction = np.stack(
        (
            np.cos(elevation) * np.sin(azimuth),
            np.cos(elevation) * np.cos(azimuth),
            np.sin(elevation),
        ),
        axis=-1,
    )
    boresight = boresight_unit_vector(pointing)
    dot = direction @ boresight
    cross = np.linalg.norm(np.cross(direction, boresight), axis=-1)
    return np.rad2deg(np.arctan2(cross, dot))


def screen_field(
    catalogue: ElementSetCatalogue,
    propagated: PropagatedWindow,
    tracks: ObservedTracks,
    *,
    pointing: BeamPointingV1,
    window: SkyWindowV1,
    downlink_frequency_hz: float,
    maximum_objects: int = MAXIMUM_REPORTED_OBJECTS,
) -> tuple[tuple[SkyObjectPredictionV1, ...], int, SkyExclusionsV1]:
    """Return the in-beam predictions, how many qualified, and what was excluded.

    An object qualifies when it is inside the cone at *any* knot of the window,
    not merely at the anchor, so a satellite crossing the beam during the window
    is reported rather than missed.
    """

    if maximum_objects < 1:
        raise ValueError("the reported-object bound must be positive")

    anchor = tracks.anchor_index
    separation = boresight_separation_deg(tracks.azimuth_deg, tracks.elevation_deg, pointing)
    minimum_separation = separation.min(axis=1)
    peak_elevation = tracks.elevation_deg.max(axis=1)

    propagation_ok = tracks.usable
    plausible = propagation_ok & (tracks.altitude_km.min(axis=1) > MINIMUM_PLAUSIBLE_ALTITUDE_KM)
    above_mask = plausible & (peak_elevation > pointing.horizon_mask_deg)
    beam_edge = pointing.half_angle_deg + _BEAM_EDGE_TOLERANCE_DEG
    in_beam = above_mask & (minimum_separation <= beam_edge)

    exclusions = SkyExclusionsV1(
        propagation_failed=int((~propagation_ok).sum()),
        implausible_altitude=int((propagation_ok & ~plausible).sum()),
        below_horizon_mask=int((plausible & ~above_mask).sum()),
        outside_beam=int((above_mask & ~in_beam).sum()),
    )

    selected = np.flatnonzero(in_beam)
    # Closest to boresight first: the operator cares which object the antenna is
    # actually looking at, not which happens to sit highest in the sky.
    order = selected[np.argsort(minimum_separation[selected], kind="stable")]
    source_count = int(order.size)
    offsets = (np.asarray(propagated.utc_ns, dtype=np.int64) - window.anchor_utc_ns).astype(
        np.float64
    ) / 1e9

    predictions: list[SkyObjectPredictionV1] = []
    for index in order[:maximum_objects]:
        shift = doppler_shift_hz(downlink_frequency_hz, tracks.range_rate_km_s[index])
        polynomial: DopplerPolynomialV1 = fit_doppler_polynomial(
            offsets,
            shift,
            downlink_frequency_hz=downlink_frequency_hz,
            reference_utc_ns=window.anchor_utc_ns,
        )
        predictions.append(
            SkyObjectPredictionV1(
                object_name=catalogue.names[index][:64],
                catalog_number=catalogue.satellite_numbers[index],
                azimuth_deg=float(tracks.azimuth_deg[index, anchor]),
                elevation_deg=float(tracks.elevation_deg[index, anchor]),
                range_km=float(tracks.range_km[index, anchor]),
                range_rate_km_s=float(tracks.range_rate_km_s[index, anchor]),
                peak_elevation_deg=float(peak_elevation[index]),
                minimum_boresight_separation_deg=float(minimum_separation[index]),
                within_beam_at_anchor=bool(
                    separation[index, anchor] <= beam_edge
                    and tracks.elevation_deg[index, anchor] > pointing.horizon_mask_deg
                ),
                doppler=polynomial,
            )
        )
    return tuple(predictions), source_count, exclusions
