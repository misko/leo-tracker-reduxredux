"""Select the catalogued objects that fall inside one antenna beam.

Discrete sampling alone cannot decide beam membership.  A grazing chord through
a cone is arbitrarily short -- an object whose closest approach is 2.99 degrees
against a 3.00 degree cone is inside it for about a third of a second, which no
practical sampling rate reliably catches.  Screening is therefore two-stage.

The coarse pass classifies each object three ways using a margin equal to the
furthest the look direction can move between samples.  An object is *definitely
in* when some sample is inside the cone by more than the margin while also
above the mask by more than the margin; *definitely out* when no sample comes
within the margin of being simultaneously eligible; and otherwise *ambiguous*.
Only the ambiguous band is re-evaluated on a fine grid, so cost stays with the
objects whose membership is genuinely in question, and no object is ever
discarded on a maybe.

The selection always accounts for what it drops.  An object leaves the report
for exactly one of four reasons, and every reason is counted, so "nothing in
the beam" can be distinguished from "nothing was considered".
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
from leo.sky.sampling import SamplingGrid, candidate_margin_deg

MAXIMUM_REPORTED_OBJECTS = 512

# The cone boundary is inclusive, and an object placed exactly on it must be
# selected deterministically rather than by whichever way the last rounding went.
# One nanodegree is far below any physically meaningful pointing accuracy.
_BEAM_EDGE_TOLERANCE_DEG = 1e-9


@dataclass(frozen=True, slots=True)
class ObservedTracks:
    """Horizon-frame tracks for the observed objects across one grid.

    Every array is shaped ``(objects, samples)``.  When the tracks cover only a
    subset of a catalogue, ``row_of`` on the caller maps catalogue index to row.
    """

    azimuth_deg: NDArray[np.float64]
    elevation_deg: NDArray[np.float64]
    range_km: NDArray[np.float64]
    range_rate_km_s: NDArray[np.float64]
    altitude_km: NDArray[np.float64]
    usable: NDArray[np.bool_]
    anchor_index: int


@dataclass(frozen=True, slots=True)
class CoarseClassification:
    """Three-way split of the catalogue produced by the coarse pass."""

    definitely_in: NDArray[np.bool_]
    ambiguous: NDArray[np.bool_]
    plausible: NDArray[np.bool_]
    ever_near_mask: NDArray[np.bool_]
    propagation_ok: NDArray[np.bool_]
    margin_deg: float

    @property
    def needs_refinement(self) -> NDArray[np.intp]:
        return np.flatnonzero(self.ambiguous)


def observe_grid(
    propagated: PropagatedWindow, observer: ObserverSiteV1, grid: SamplingGrid
) -> ObservedTracks:
    """Convert a propagated grid into observer-relative tracks."""

    julian_day, fraction = julian_day_from_utc_ns(np.asarray(grid.utc_ns, dtype=np.int64))
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
    return ObservedTracks(
        azimuth_deg=azimuth,
        elevation_deg=elevation,
        range_km=slant,
        range_rate_km_s=rate,
        altitude_km=altitude,
        usable=propagated.usable,
        anchor_index=grid.anchor_index,
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


def eligible_at_each_sample(
    tracks: ObservedTracks, pointing: BeamPointingV1, *, margin_deg: float = 0.0
) -> NDArray[np.bool_]:
    """Per-sample eligibility, relaxed (or tightened) by an angular margin.

    Both conditions are evaluated at the same sample and only then reduced.
    Reducing them independently -- peak elevation against minimum separation --
    would admit an object inside the cone at one instant and above the mask at
    a different one, having been observable at neither.
    """

    separation = boresight_separation_deg(tracks.azimuth_deg, tracks.elevation_deg, pointing)
    edge = pointing.half_angle_deg + _BEAM_EDGE_TOLERANCE_DEG + margin_deg
    mask = pointing.horizon_mask_deg - margin_deg
    return (separation <= edge) & (tracks.elevation_deg > mask)


def classify_coarse(
    tracks: ObservedTracks, pointing: BeamPointingV1, grid: SamplingGrid
) -> CoarseClassification:
    """Split the catalogue into definitely-in, ambiguous and definitely-out.

    The margin is the furthest the look direction can move between two samples.
    An object outside the relaxed cone at every sample therefore cannot have
    entered the true cone between samples, which is what makes the coarse pass
    free of false negatives however brief the transit.
    """

    margin = candidate_margin_deg(grid)
    propagation_ok = tracks.usable
    plausible = propagation_ok & (tracks.altitude_km.min(axis=1) > MINIMUM_PLAUSIBLE_ALTITUDE_KM)
    ever_near_mask = plausible & (
        tracks.elevation_deg.max(axis=1) > pointing.horizon_mask_deg - margin
    )

    strict = eligible_at_each_sample(tracks, pointing, margin_deg=-margin).any(axis=1)
    relaxed = eligible_at_each_sample(tracks, pointing, margin_deg=margin).any(axis=1)

    return CoarseClassification(
        definitely_in=plausible & strict,
        ambiguous=plausible & relaxed & ~strict,
        plausible=plausible,
        ever_near_mask=ever_near_mask,
        propagation_ok=propagation_ok,
        margin_deg=margin,
    )


def build_predictions(
    catalogue: ElementSetCatalogue,
    tracks: ObservedTracks,
    grid: SamplingGrid,
    *,
    indices: NDArray[np.intp],
    pointing: BeamPointingV1,
    downlink_frequency_hz: float,
    element_epoch_utc_ns: tuple[int, ...],
    row_of: dict[int, int] | None = None,
    maximum_objects: int = MAXIMUM_REPORTED_OBJECTS,
    eligibility_margin_deg: float = 0.0,
) -> tuple[SkyObjectPredictionV1, ...]:
    """Build bounded predictions for the selected objects, closest first.

    ``eligibility_margin_deg`` must match the margin the selection was made
    with.  An object selected on a finer grid than the one being reported from
    can have no eligible sample here, and the closest-observable reduction would
    then be infinite -- which the report contract rightly refuses.  The margin
    keeps the two consistent, and the fallback below guarantees a finite value
    even if a future caller gets that pairing wrong.
    """

    if maximum_objects < 1:
        raise ValueError("the reported-object bound must be positive")

    eligible = eligible_at_each_sample(tracks, pointing, margin_deg=eligibility_margin_deg)
    separation = boresight_separation_deg(tracks.azimuth_deg, tracks.elevation_deg, pointing)
    observable_separation = np.where(eligible, separation, np.inf).min(axis=1)
    observable_separation = np.where(
        np.isfinite(observable_separation), observable_separation, separation.min(axis=1)
    )
    peak_elevation = tracks.elevation_deg.max(axis=1)
    anchor = tracks.anchor_index
    offsets = np.asarray(grid.offsets_s(), dtype=np.float64)
    anchor_utc_ns = grid.anchor_utc_ns

    def row_for(index: int) -> int:
        return row_of[index] if row_of is not None else index

    ordered = sorted(
        (int(index) for index in indices),
        key=lambda index: (float(observable_separation[row_for(index)]), index),
    )
    predictions: list[SkyObjectPredictionV1] = []
    for index in ordered[:maximum_objects]:
        row = row_for(index)
        shift = doppler_shift_hz(downlink_frequency_hz, tracks.range_rate_km_s[row])
        polynomial: DopplerPolynomialV1 = fit_doppler_polynomial(
            offsets,
            shift,
            downlink_frequency_hz=downlink_frequency_hz,
            reference_utc_ns=anchor_utc_ns,
        )
        epoch_ns = element_epoch_utc_ns[index]
        predictions.append(
            SkyObjectPredictionV1(
                object_name=catalogue.names[index][:64],
                catalog_number=catalogue.satellite_numbers[index],
                azimuth_deg=float(tracks.azimuth_deg[row, anchor]),
                elevation_deg=float(tracks.elevation_deg[row, anchor]),
                range_km=float(tracks.range_km[row, anchor]),
                range_rate_km_s=float(tracks.range_rate_km_s[row, anchor]),
                peak_elevation_deg=float(peak_elevation[row]),
                minimum_boresight_separation_deg=float(observable_separation[row]),
                within_beam_at_anchor=bool(eligible[row, anchor]),
                boundary_uncertain=bool(
                    eligibility_margin_deg > 0.0
                    and observable_separation[row]
                    > pointing.half_angle_deg - eligibility_margin_deg
                ),
                element_epoch_utc_ns=epoch_ns,
                element_age_s=abs(anchor_utc_ns - epoch_ns) / 1e9,
                doppler=polynomial,
            )
        )
    return tuple(predictions)


def summarise_exclusions(
    classification: CoarseClassification, selected: NDArray[np.bool_]
) -> SkyExclusionsV1:
    """Account for every catalogued object exactly once."""

    propagation_ok = classification.propagation_ok
    plausible = classification.plausible
    near_mask = classification.ever_near_mask
    return SkyExclusionsV1(
        propagation_failed=int((~propagation_ok).sum()),
        implausible_altitude=int((propagation_ok & ~plausible).sum()),
        below_horizon_mask=int((plausible & ~near_mask).sum()),
        outside_beam=int((near_mask & ~selected).sum()),
    )
