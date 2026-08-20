"""Bounded presentation projections for the sky interface.

Shared by the CLI and the read-only API so that one shape is defined once and
both surfaces necessarily agree.  These carry no catalog, storage or HTTP
identity; they project the reviewed site registry and the element-set archive
into something a reader can display.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
import math
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from leo.contracts.base import ContractModel
from leo.contracts.digests import Sha256Digest
from leo.contracts.sky import ObserverSiteV1, SkyWindowV1, TleSnapshotRefV1
from leo.operations.tle_archive import TleSnapshotRef
from leo.sky.sites import SITE_PRESETS, SitePreset, preset_names

MAXIMUM_LISTED_SNAPSHOTS = 200

# Upper edge of the radio spectrum (EHF).  The science contracts only require a
# positive transmit frequency, which is correct for them, but a surface that
# accepts 1e308 lets the Doppler arithmetic overflow to infinity and fail deep
# inside the fit.  Both surfaces apply this same bound so a value accepted by
# one is accepted by the other.
MAXIMUM_DOWNLINK_FREQUENCY_HZ = 3.0e11


class SkySiteRowV1(ContractModel):
    """One reviewed observer preset, with the provenance of its coordinates."""

    schema_version: Literal[1] = 1
    name: str
    label: str
    latitude_deg: Annotated[float, Field(ge=-90.0, le=90.0)]
    longitude_deg: Annotated[float, Field(gt=-180.0, le=180.0)]
    altitude_m: float
    position_uncertainty_m: Annotated[float, Field(ge=0.0)]
    provenance: str


class SkySiteListV1(ContractModel):
    schema_version: Literal[1] = 1
    sites: tuple[SkySiteRowV1, ...]


class SkySnapshotRowV1(ContractModel):
    """One archived element-set snapshot, identified by collection time and digest."""

    schema_version: Literal[1] = 1
    provider: Literal["space-track", "huggingface"]
    collected_utc: datetime
    collected_utc_ns: Annotated[int, Field(gt=0)]
    digest: Sha256Digest
    byte_size: Annotated[int, Field(ge=0)]


class SkySnapshotListV1(ContractModel):
    schema_version: Literal[1] = 1
    archive_root: str
    returned_count: Annotated[int, Field(ge=0)]
    source_count: Annotated[int, Field(ge=0)]
    truncated: bool
    snapshots: Annotated[tuple[SkySnapshotRowV1, ...], Field(max_length=MAXIMUM_LISTED_SNAPSHOTS)]


def site_row(preset: SitePreset) -> SkySiteRowV1:
    return SkySiteRowV1(
        name=preset.name,
        label=preset.label,
        latitude_deg=preset.latitude_deg,
        longitude_deg=preset.longitude_deg,
        altitude_m=preset.altitude_m,
        position_uncertainty_m=preset.position_uncertainty_m,
        provenance=preset.provenance,
    )


def site_list() -> SkySiteListV1:
    """Project the reviewed preset registry in stable order."""

    return SkySiteListV1(sites=tuple(site_row(SITE_PRESETS[name]) for name in preset_names()))


def snapshot_row(reference: TleSnapshotRef) -> SkySnapshotRowV1:
    return SkySnapshotRowV1(
        provider=reference.provider,  # type: ignore[arg-type]
        collected_utc=datetime.fromtimestamp(reference.collected_utc_ns / 1e9, UTC),
        collected_utc_ns=reference.collected_utc_ns,
        digest=reference.digest,
        byte_size=reference.byte_size,
    )


def snapshot_list(
    archive_root: str, references: Sequence[TleSnapshotRef], *, limit: int
) -> SkySnapshotListV1:
    """Project the newest ``limit`` snapshots, reporting what was left out."""

    if not 1 <= limit <= MAXIMUM_LISTED_SNAPSHOTS:
        raise ValueError(f"snapshot limit must be between 1 and {MAXIMUM_LISTED_SNAPSHOTS}")
    selected = tuple(references[-limit:])
    return SkySnapshotListV1(
        archive_root=archive_root,
        returned_count=len(selected),
        source_count=len(references),
        truncated=len(selected) < len(references),
        snapshots=tuple(snapshot_row(item) for item in selected),
    )


# Globe and dome views ship one track per object rather than a frame per
# instant, so the browser can interpolate between knots instead of refetching.
MAXIMUM_GLOBE_OBJECTS = 12_000
MAXIMUM_VIEW_SAMPLES = 33

# ECEF coordinates are quantised to signed 16-bit counts of this many kilometres.
# The range covers +-8,000 km, comfortably beyond any low-Earth orbit, and one
# count is 244 m -- about a fiftieth of a pixel on a 1,000 px globe.
GLOBE_QUANTUM_KM = 8_000.0 / 32_767.0


class GlobeTrackV1(ContractModel):
    """One object's quantised ECEF path across the window.

    ``positions`` is flattened ``[x0, y0, z0, x1, y1, z1, ...]`` in units of
    :data:`GLOBE_QUANTUM_KM`, three entries per knot.  Integers keep the payload
    small and compress well; the browser scales them back and interpolates.
    """

    schema_version: Literal[1] = 1
    catalog_number: Annotated[int, Field(ge=1)]
    object_name: Annotated[str, Field(min_length=1, max_length=64)]
    positions: tuple[int, ...]

    @model_validator(mode="after")
    def _positions_are_whole_knots(self) -> Self:
        if not self.positions or len(self.positions) % 3:
            raise ValueError("globe positions must hold three coordinates per knot")
        if any(abs(value) > 32_767 for value in self.positions):
            raise ValueError("globe positions must fit a signed 16-bit quantisation")
        return self


class GlobeFrameSetV1(ContractModel):
    """Quantised ECEF tracks for every rendered object over one window."""

    schema_version: Literal[1] = 1
    window: SkyWindowV1
    knot_utc_ns: tuple[int, ...]
    quantum_km: Annotated[float, Field(gt=0.0)]
    earth_radius_km: Annotated[float, Field(gt=0.0)]
    snapshot: TleSnapshotRefV1
    tracks: Annotated[tuple[GlobeTrackV1, ...], Field(max_length=MAXIMUM_GLOBE_OBJECTS)]
    returned_object_count: Annotated[int, Field(ge=0)]
    source_object_count: Annotated[int, Field(ge=0)]
    truncated: bool

    @model_validator(mode="after")
    def _counts_and_knots_agree(self) -> Self:
        if self.returned_object_count != len(self.tracks):
            raise ValueError("returned object count disagrees with the track inventory")
        if self.truncated != (self.returned_object_count < self.source_object_count):
            raise ValueError("truncation flag disagrees with the returned inventory")
        if len(self.knot_utc_ns) < 2:
            raise ValueError("a globe frame set needs at least two knots")
        expected = 3 * len(self.knot_utc_ns)
        if any(len(track.positions) != expected for track in self.tracks):
            raise ValueError("every track must cover exactly the declared knots")
        return self


class SkyViewTrackV1(ContractModel):
    """One object's horizon-frame path as seen from the pinned observer."""

    schema_version: Literal[1] = 1
    catalog_number: Annotated[int, Field(ge=1)]
    object_name: Annotated[str, Field(min_length=1, max_length=64)]
    azimuth_deg: tuple[float, ...]
    elevation_deg: tuple[float, ...]
    range_km: tuple[float, ...]
    peak_elevation_deg: Annotated[float, Field(ge=-90.0, le=90.0)]

    @model_validator(mode="after")
    def _samples_are_aligned_and_finite(self) -> Self:
        if not (len(self.azimuth_deg) == len(self.elevation_deg) == len(self.range_km)):
            raise ValueError("sky-view sample arrays must be the same length")
        if not self.azimuth_deg:
            raise ValueError("a sky-view track needs at least one sample")
        for series in (self.azimuth_deg, self.elevation_deg, self.range_km):
            if any(not math.isfinite(value) for value in series):
                raise ValueError("sky-view samples must be finite")
        if self.peak_elevation_deg + 1e-9 < max(self.elevation_deg):
            raise ValueError("peak elevation is below a reported sample")
        return self


class SkyViewFrameSetV1(ContractModel):
    """Horizon-frame tracks for the objects visible from one observer."""

    schema_version: Literal[1] = 1
    observer: ObserverSiteV1
    window: SkyWindowV1
    knot_utc_ns: tuple[int, ...]
    horizon_mask_deg: Annotated[float, Field(ge=0.0, le=90.0)]
    snapshot: TleSnapshotRefV1
    tracks: Annotated[tuple[SkyViewTrackV1, ...], Field(max_length=MAXIMUM_GLOBE_OBJECTS)]
    returned_object_count: Annotated[int, Field(ge=0)]
    source_object_count: Annotated[int, Field(ge=0)]
    truncated: bool

    @model_validator(mode="after")
    def _counts_and_knots_agree(self) -> Self:
        if self.returned_object_count != len(self.tracks):
            raise ValueError("returned object count disagrees with the track inventory")
        if self.truncated != (self.returned_object_count < self.source_object_count):
            raise ValueError("truncation flag disagrees with the returned inventory")
        if any(len(track.azimuth_deg) != len(self.knot_utc_ns) for track in self.tracks):
            raise ValueError("every track must cover exactly the declared knots")
        return self
