"""Bounded presentation projections for the sky interface.

Shared by the CLI and the read-only API so that one shape is defined once and
both surfaces necessarily agree.  These carry no catalog, storage or HTTP
identity; they project the reviewed site registry and the element-set archive
into something a reader can display.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Annotated, Literal

from pydantic import Field

from leo.contracts.base import ContractModel
from leo.contracts.digests import Sha256Digest
from leo.operations.tle_archive import TleSnapshotRef
from leo.sky.sites import SITE_PRESETS, SitePreset, preset_names

MAXIMUM_LISTED_SNAPSHOTS = 200


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
