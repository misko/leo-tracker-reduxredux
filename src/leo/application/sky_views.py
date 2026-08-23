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

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime

import numpy as np

from leo.application.sky_field import ResolvedSnapshot, SkyFieldService, SkyFieldUnavailableError
from leo.contracts.sky import ObserverSiteV1, SkyWindowV1, TleSnapshotRefV1
from leo.operations.tle_archive import TleArchiveError
from leo.presentation.sky import (
    GLOBE_QUANTUM_KM,
    MAXIMUM_GLOBE_OBJECTS,
    MAXIMUM_LISTED_SNAPSHOTS,
    MAXIMUM_TLE_COMPARISON_ENTRIES,
    MAXIMUM_VIEW_SAMPLES,
    SKY_VIEW_DOPPLER_CHANNEL_CENTERS_HZ,
    TLE_PROVIDER_SOURCES,
    GlobeFrameSetV1,
    GlobeTrackV1,
    OrbitElementsV1,
    SkyViewDopplerRateV1,
    SkyViewFrameSetV1,
    SkyViewObjectDetailV1,
    SkyViewTleComparisonV1,
    SkyViewTrackV1,
    TleArchiveListV1,
    TleArchiveRowV1,
    TlePositionComparisonRowV1,
)
from leo.sky.doppler import average_doppler_rate_hz_s, doppler_shift_hz
from leo.sky.frames import (
    WGS84_SEMI_MAJOR_AXIS_KM,
    greenwich_mean_sidereal_time_rad,
    julian_day_from_utc_ns,
    teme_to_ecef,
)
from leo.sky.propagation import (
    MINIMUM_PLAUSIBLE_ALTITUDE_KM,
    ElementSetError,
    ElementSetRecord,
    count_element_sets,
    find_element_set_record,
    parse_element_sets,
    propagate_grid,
)
from leo.sky.sampling import SamplingGrid, presentation_grid
from leo.sky.screening import observe_grid

_NS_PER_S = 1_000_000_000
_INT16_LIMIT = 32_767
_MAXIMUM_COMPARISON_SNAPSHOTS = 200


@dataclass(frozen=True, slots=True)
class _ObjectPosition:
    position_ecef_km: np.ndarray
    azimuth_deg: float
    elevation_deg: float
    range_km: float
    element_epoch_utc_ns: int


def _element_digest(record: ElementSetRecord) -> str:
    payload = f"{record.first_line}\n{record.second_line}\n".encode("ascii")
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _object_position(
    record: ElementSetRecord,
    *,
    observer: ObserverSiteV1,
    window: SkyWindowV1,
) -> _ObjectPosition:
    catalogue = parse_element_sets(record.text)
    grid = _view_grid(_view_window(window, 3))
    propagated = propagate_grid(catalogue, grid)
    observed = observe_grid(propagated, observer, grid)
    if not observed.usable[0] or (observed.altitude_km[0].min() <= MINIMUM_PLAUSIBLE_ALTITUDE_KM):
        raise SkyFieldUnavailableError(
            f"catalog object {record.satellite_number} cannot be propagated"
        )
    julian_day, fraction = julian_day_from_utc_ns(np.asarray(grid.utc_ns, dtype=np.int64))
    gmst = greenwich_mean_sidereal_time_rad(julian_day, fraction)
    position, _ = teme_to_ecef(
        propagated.position_teme_km,
        propagated.velocity_teme_km_s,
        gmst[None, :],
    )
    anchor = grid.anchor_index
    return _ObjectPosition(
        position_ecef_km=position[0, anchor],
        azimuth_deg=float(observed.azimuth_deg[0, anchor]),
        elevation_deg=float(observed.elevation_deg[0, anchor]),
        range_km=float(observed.range_km[0, anchor]),
        element_epoch_utc_ns=catalogue.element_epoch_utc_ns()[0],
    )


def _look_angle_difference_deg(first: _ObjectPosition, second: _ObjectPosition) -> float:
    def unit(position: _ObjectPosition) -> np.ndarray:
        azimuth = np.deg2rad(position.azimuth_deg)
        elevation = np.deg2rad(position.elevation_deg)
        return np.asarray(
            (
                np.cos(elevation) * np.sin(azimuth),
                np.cos(elevation) * np.cos(azimuth),
                np.sin(elevation),
            ),
            dtype=np.float64,
        )

    left = unit(first)
    right = unit(second)
    return float(
        np.rad2deg(np.arctan2(np.linalg.norm(np.cross(left, right)), float(np.dot(left, right))))
    )


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
    range_rate_km_s: np.ndarray,
    offsets_s: np.ndarray,
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
        predicted_doppler_rates=tuple(
            SkyViewDopplerRateV1(
                starlink_channel=channel,
                center_frequency_hz=center_frequency_hz,
                average_rate_hz_s=round(
                    average_doppler_rate_hz_s(
                        float(center_frequency_hz), range_rate_km_s, offsets_s
                    ),
                    6,
                ),
            )
            for channel, center_frequency_hz in SKY_VIEW_DOPPLER_CHANNEL_CENTERS_HZ
        ),
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

    def tle_inventory(self, *, limit: int = MAXIMUM_LISTED_SNAPSHOTS) -> TleArchiveListV1:
        """Describe verified local snapshots, including their record counts."""

        if not 1 <= limit <= MAXIMUM_LISTED_SNAPSHOTS:
            raise ValueError(
                f"TLE inventory limit must be between 1 and {MAXIMUM_LISTED_SNAPSHOTS}"
            )
        try:
            references = self._field.archive.list_snapshots()
            if not references:
                raise SkyFieldUnavailableError("no TLE snapshot is available")
            selected = tuple(reversed(references[-limit:]))
            rows: list[TleArchiveRowV1] = []
            for reference in selected:
                satellite_count = count_element_sets(self._field.archive.read(reference))
                source_label, source_url = TLE_PROVIDER_SOURCES[reference.provider]
                rows.append(
                    TleArchiveRowV1(
                        provider=reference.provider,  # type: ignore[arg-type]
                        source_label=source_label,
                        source_url=source_url,
                        collected_utc=datetime.fromtimestamp(reference.collected_utc_ns / 1e9, UTC),
                        collected_utc_ns=reference.collected_utc_ns,
                        digest=reference.digest,
                        byte_size=reference.byte_size,
                        satellite_count=satellite_count,
                    )
                )
        except (TleArchiveError, ElementSetError) as error:
            raise SkyFieldUnavailableError(str(error)) from error
        return TleArchiveListV1(
            archive_root=str(self._field.archive.root),
            returned_count=len(rows),
            source_count=len(references),
            truncated=len(rows) < len(references),
            snapshots=tuple(rows),
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
        offsets_s = np.asarray(grid.offsets_s(), dtype=np.float64)

        rows = tuple(
            _sky_view_track(
                catalog_number=catalogue.satellite_numbers[int(index)],
                object_name=catalogue.names[int(index)][:64],
                azimuth_deg=tracks_all.azimuth_deg[index],
                elevation_deg=tracks_all.elevation_deg[index],
                range_km=tracks_all.range_km[index],
                range_rate_km_s=tracks_all.range_rate_km_s[index],
                offsets_s=offsets_s,
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

    def object_detail(
        self,
        *,
        observer: ObserverSiteV1,
        window: SkyWindowV1,
        catalog_number: int,
        downlink_frequency_hz: float,
        sample_count: int = 9,
        provider: str | None = None,
        snapshot_digest: str | None = None,
    ) -> SkyViewObjectDetailV1:
        """Return bounded orbital and Doppler detail for one selected object."""

        window = _view_window(window, sample_count)
        catalogue, resolved = self._catalogue(window, provider)
        if snapshot_digest is not None and resolved.reference.digest != snapshot_digest:
            raise SkyFieldUnavailableError("the element-set snapshot used by the view changed")
        try:
            index = catalogue.satellite_numbers.index(catalog_number)
        except ValueError as error:
            raise ValueError(f"catalog object {catalog_number} is not in the snapshot") from error

        grid = _view_grid(window)
        propagated = propagate_grid(catalogue, grid, indices=(index,))
        observed = observe_grid(propagated, observer, grid)
        if not observed.usable[0] or (
            observed.altitude_km[0].min() <= MINIMUM_PLAUSIBLE_ALTITUDE_KM
        ):
            raise SkyFieldUnavailableError(f"catalog object {catalog_number} cannot be propagated")

        satellite = catalogue.satellites[index]
        radians_to_degrees = 180.0 / np.pi
        mean_motion_rev_day = float(satellite.no_kozai * 1_440.0 / (2.0 * np.pi))
        shift = doppler_shift_hz(downlink_frequency_hz, observed.range_rate_km_s[0])
        return SkyViewObjectDetailV1(
            observer=observer,
            window=window,
            knot_utc_ns=grid.utc_ns,
            snapshot=self._snapshot_ref(resolved, len(catalogue)),
            catalog_number=catalog_number,
            object_name=catalogue.names[index][:64],
            orbit=OrbitElementsV1(
                element_epoch_utc_ns=catalogue.element_epoch_utc_ns()[index],
                inclination_deg=float(satellite.inclo * radians_to_degrees),
                right_ascension_deg=float(satellite.nodeo * radians_to_degrees) % 360.0,
                eccentricity=float(satellite.ecco),
                argument_of_perigee_deg=float(satellite.argpo * radians_to_degrees) % 360.0,
                mean_anomaly_deg=float(satellite.mo * radians_to_degrees) % 360.0,
                mean_motion_rev_day=mean_motion_rev_day,
                period_minutes=1_440.0 / mean_motion_rev_day,
                perigee_altitude_km=float(satellite.altp * satellite.radiusearthkm),
                apogee_altitude_km=float(satellite.alta * satellite.radiusearthkm),
            ),
            downlink_frequency_hz=downlink_frequency_hz,
            range_rate_km_s=tuple(round(float(value), 7) for value in observed.range_rate_km_s[0]),
            doppler_shift_hz=tuple(round(float(value), 3) for value in shift),
        )

    def object_tle_comparison(
        self,
        *,
        observer: ObserverSiteV1,
        window: SkyWindowV1,
        catalog_number: int,
        provider: str,
        snapshot_digest: str,
    ) -> SkyViewTleComparisonV1:
        """Compare the newest unique element sets with the one used by the view."""

        catalogue, resolved = self._catalogue(window, provider)
        if resolved.reference.digest != snapshot_digest:
            raise SkyFieldUnavailableError("the element-set snapshot used by the view changed")
        try:
            view_index = catalogue.satellite_numbers.index(catalog_number)
        except ValueError as error:
            raise ValueError(f"catalog object {catalog_number} is not in the snapshot") from error

        try:
            view_record = find_element_set_record(resolved.text, catalog_number)
            if view_record is None:
                raise ElementSetError(f"catalog object {catalog_number} is not in the snapshot")
            view_position = _object_position(view_record, observer=observer, window=window)
            references = self._field.archive.list_snapshots()
            selected_references = list(reversed(references[-_MAXIMUM_COMPARISON_SNAPSHOTS:]))
            if resolved.reference not in selected_references:
                if len(selected_references) == _MAXIMUM_COMPARISON_SNAPSHOTS:
                    selected_references[-1] = resolved.reference
                else:
                    selected_references.append(resolved.reference)
                selected_references.sort(reverse=True)

            seen: set[str] = set()
            rows: list[TlePositionComparisonRowV1] = []
            for reference in selected_references:
                record = find_element_set_record(
                    self._field.archive.read(reference), catalog_number
                )
                if record is None:
                    continue
                digest = _element_digest(record)
                if digest in seen:
                    continue
                seen.add(digest)
                position = _object_position(record, observer=observer, window=window)
                source_label, _ = TLE_PROVIDER_SOURCES[reference.provider]
                rows.append(
                    TlePositionComparisonRowV1(
                        provider=reference.provider,  # type: ignore[arg-type]
                        source_label=source_label,
                        collected_utc_ns=reference.collected_utc_ns,
                        snapshot_digest=reference.digest,
                        element_digest=digest,
                        element_epoch_utc_ns=position.element_epoch_utc_ns,
                        is_view_element=digest == _element_digest(view_record),
                        position_ecef_km=(
                            round(float(position.position_ecef_km[0]), 6),
                            round(float(position.position_ecef_km[1]), 6),
                            round(float(position.position_ecef_km[2]), 6),
                        ),
                        azimuth_deg=round(position.azimuth_deg, 6),
                        elevation_deg=round(position.elevation_deg, 6),
                        range_km=round(position.range_km, 6),
                        position_difference_km=round(
                            float(
                                np.linalg.norm(
                                    position.position_ecef_km - view_position.position_ecef_km
                                )
                            ),
                            6,
                        ),
                        look_angle_difference_deg=round(
                            _look_angle_difference_deg(position, view_position), 6
                        ),
                        range_difference_km=round(position.range_km - view_position.range_km, 6),
                    )
                )
                if len(rows) == MAXIMUM_TLE_COMPARISON_ENTRIES:
                    break
        except (TleArchiveError, ElementSetError) as error:
            raise SkyFieldUnavailableError(str(error)) from error
        if not rows:
            raise SkyFieldUnavailableError(
                f"no archived TLE entry is available for catalog object {catalog_number}"
            )

        return SkyViewTleComparisonV1(
            observer=observer,
            anchor_utc_ns=window.anchor_utc_ns,
            catalog_number=catalog_number,
            object_name=catalogue.names[view_index][:64],
            view_snapshot=self._snapshot_ref(resolved, len(catalogue)),
            view_element_digest=_element_digest(view_record),
            view_element_epoch_utc_ns=view_position.element_epoch_utc_ns,
            archive_snapshot_count=len(references),
            searched_snapshot_count=len(selected_references),
            search_truncated=len(selected_references) < len(references),
            entries=tuple(rows),
        )
