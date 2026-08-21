"""Build the globe and ground-to-sky projections the browser renders.

These are *views*, not evidence.  The authoritative answer to "what is in the
beam" is :class:`leo.application.sky_field.SkyFieldService`; these projections
exist so a person can see the same sky, and they are deliberately coarser: a
handful of knots per object, quantised, for the browser to interpolate between.

Propagation stays on the server.  The browser receives positions and draws
them; it runs no orbital mechanics, so there is no second implementation whose
agreement has to be maintained.
"""

from __future__ import annotations

import numpy as np

from leo.application.sky_field import ResolvedSnapshot, SkyFieldService, SkyFieldUnavailableError
from leo.contracts.sky import ObserverSiteV1, SkyWindowV1, TleSnapshotRefV1
from leo.presentation.sky import (
    GLOBE_QUANTUM_KM,
    MAXIMUM_GLOBE_OBJECTS,
    MAXIMUM_VIEW_SAMPLES,
    GlobeFrameSetV1,
    GlobeTrackV1,
    SkyViewFrameSetV1,
    SkyViewTrackV1,
)
from leo.sky.frames import (
    WGS84_SEMI_MAJOR_AXIS_KM,
    greenwich_mean_sidereal_time_rad,
    julian_day_from_utc_ns,
    teme_to_ecef,
)
from leo.sky.propagation import (
    MINIMUM_PLAUSIBLE_ALTITUDE_KM,
    ElementSetError,
    parse_element_sets,
    propagate_grid,
)
from leo.sky.sampling import SamplingGrid, presentation_grid
from leo.sky.screening import observe_grid

_NS_PER_S = 1_000_000_000
_INT16_LIMIT = 32_767


def _view_window(window: SkyWindowV1, sample_count: int) -> SkyWindowV1:
    """Return the window the view is actually sampled on.

    The request's sample count belongs *in* the window rather than beside it.
    Building a real ``SkyWindowV1`` means the same validators apply -- odd
    counts so the anchor is sampled, and knots that divide the span exactly --
    and the document cannot then describe one grid while carrying another.

    View sampling is independent of the screening resolution: a browser
    interpolating a smooth arc needs far fewer points than a decision about
    whether an object crossed a cone.
    """

    if not 3 <= sample_count <= MAXIMUM_VIEW_SAMPLES:
        raise ValueError(f"view sample count must be between 3 and {MAXIMUM_VIEW_SAMPLES}")
    return window.model_validate(
        {
            "anchor_utc_ns": window.anchor_utc_ns,
            "half_width_s": window.half_width_s,
            "sample_count": sample_count,
        }
    )


def _view_grid(window: SkyWindowV1) -> SamplingGrid:
    """The sampling grid a view window describes."""

    return presentation_grid(window)


def _sky_view_track(
    *,
    catalog_number: int,
    object_name: str,
    azimuth_deg: np.ndarray,
    elevation_deg: np.ndarray,
    range_km: np.ndarray,
) -> SkyViewTrackV1:
    """Build one track, deriving the peak from the samples as published.

    Samples are rounded to keep the payload small, and the peak must be taken
    from the rounded series: rounding a sample upwards can otherwise lift it
    above a peak computed from the full-precision values, which is a real
    inconsistency however small.
    """

    elevations = tuple(round(float(value), 4) for value in elevation_deg)
    return SkyViewTrackV1(
        catalog_number=catalog_number,
        object_name=object_name,
        azimuth_deg=tuple(round(float(value), 4) for value in azimuth_deg),
        elevation_deg=elevations,
        range_km=tuple(round(float(value), 3) for value in range_km),
        peak_elevation_deg=max(elevations),
    )


class SkyViewService:
    """Project the archived constellation into browser-renderable tracks."""

    def __init__(self, field: SkyFieldService) -> None:
        self._field = field

    def _catalogue(self, window: SkyWindowV1, provider: str | None):
        resolved: ResolvedSnapshot = self._field.resolve_snapshot(
            window.anchor_utc_ns, provider=provider
        )
        try:
            catalogue = parse_element_sets(resolved.text)
        except ElementSetError as error:
            raise SkyFieldUnavailableError(
                f"snapshot {resolved.reference.path.name} is not usable: {error}"
            ) from error
        return catalogue, resolved

    @staticmethod
    def _snapshot_ref(resolved: ResolvedSnapshot, object_count: int) -> TleSnapshotRefV1:
        return TleSnapshotRefV1(
            provider=resolved.reference.provider,  # type: ignore[arg-type]
            collected_utc_ns=resolved.reference.collected_utc_ns,
            digest=resolved.reference.digest,
            object_count=object_count,
        )

    def globe(
        self,
        *,
        window: SkyWindowV1,
        sample_count: int = 5,
        limit: int = MAXIMUM_GLOBE_OBJECTS,
        provider: str | None = None,
    ) -> GlobeFrameSetV1:
        """Quantised ECEF tracks for the constellation over the window."""

        if not 1 <= limit <= MAXIMUM_GLOBE_OBJECTS:
            raise ValueError(f"globe limit must be between 1 and {MAXIMUM_GLOBE_OBJECTS}")
        window = _view_window(window, sample_count)
        catalogue, resolved = self._catalogue(window, provider)
        grid = _view_grid(window)
        propagated = propagate_grid(catalogue, grid)
        julian_day, fraction = julian_day_from_utc_ns(np.asarray(grid.utc_ns, dtype=np.int64))
        gmst = greenwich_mean_sidereal_time_rad(julian_day, fraction)
        position, _ = teme_to_ecef(
            propagated.position_teme_km, propagated.velocity_teme_km_s, gmst[None, :]
        )
        altitude = np.linalg.norm(position, axis=-1) - WGS84_SEMI_MAJOR_AXIS_KM
        # The same plausibility guard the field report applies: the live archive
        # contains decaying objects that would otherwise be drawn inside the
        # atmosphere.
        usable = propagated.usable & (altitude.min(axis=1) > MINIMUM_PLAUSIBLE_ALTITUDE_KM)
        quantised = np.rint(position / GLOBE_QUANTUM_KM).astype(np.int64)
        usable &= (np.abs(quantised) <= _INT16_LIMIT).all(axis=(1, 2))

        selected = np.flatnonzero(usable)
        tracks = tuple(
            GlobeTrackV1(
                catalog_number=catalogue.satellite_numbers[int(index)],
                object_name=catalogue.names[int(index)][:64],
                positions=tuple(int(value) for value in quantised[index].reshape(-1)),
            )
            for index in selected[:limit]
        )
        return GlobeFrameSetV1(
            window=window,
            knot_utc_ns=grid.utc_ns,
            quantum_km=GLOBE_QUANTUM_KM,
            earth_radius_km=WGS84_SEMI_MAJOR_AXIS_KM,
            snapshot=self._snapshot_ref(resolved, len(catalogue)),
            tracks=tracks,
            returned_object_count=len(tracks),
            source_object_count=int(selected.size),
            truncated=len(tracks) < int(selected.size),
        )

    def sky_view(
        self,
        *,
        observer: ObserverSiteV1,
        window: SkyWindowV1,
        horizon_mask_deg: float = 0.0,
        sample_count: int = 9,
        limit: int = MAXIMUM_GLOBE_OBJECTS,
        provider: str | None = None,
    ) -> SkyViewFrameSetV1:
        """Horizon-frame tracks for everything that rises above the mask."""

        if not 0.0 <= horizon_mask_deg <= 90.0:
            raise ValueError("horizon mask must be between 0 and 90 degrees")
        if not 1 <= limit <= MAXIMUM_GLOBE_OBJECTS:
            raise ValueError(f"sky-view limit must be between 1 and {MAXIMUM_GLOBE_OBJECTS}")
        window = _view_window(window, sample_count)
        catalogue, resolved = self._catalogue(window, provider)
        grid = _view_grid(window)
        propagated = propagate_grid(catalogue, grid)
        tracks_all = observe_grid(propagated, observer, grid)

        peak = tracks_all.elevation_deg.max(axis=1)
        usable = tracks_all.usable & (
            tracks_all.altitude_km.min(axis=1) > MINIMUM_PLAUSIBLE_ALTITUDE_KM
        )
        visible = usable & (peak > horizon_mask_deg)
        # Highest first: the objects a person looking up would notice.
        order = np.flatnonzero(visible)[np.argsort(-peak[np.flatnonzero(visible)], kind="stable")]

        rows = tuple(
            _sky_view_track(
                catalog_number=catalogue.satellite_numbers[int(index)],
                object_name=catalogue.names[int(index)][:64],
                azimuth_deg=tracks_all.azimuth_deg[index],
                elevation_deg=tracks_all.elevation_deg[index],
                range_km=tracks_all.range_km[index],
            )
            for index in order[:limit]
        )
        return SkyViewFrameSetV1(
            observer=observer,
            window=window,
            knot_utc_ns=grid.utc_ns,
            horizon_mask_deg=horizon_mask_deg,
            snapshot=self._snapshot_ref(resolved, len(catalogue)),
            tracks=rows,
            returned_object_count=len(rows),
            source_object_count=int(order.size),
            truncated=len(rows) < int(order.size),
        )
