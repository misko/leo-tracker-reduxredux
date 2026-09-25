"""Digest-pinned capture path authority selection for catalog reconciliation."""

from __future__ import annotations

from dataclasses import dataclass

from leo.contracts.recording import RecordingManifestV1
from leo.contracts.states import SourceType
from leo.station.authority import (
    CaptureHardwareBindingV1,
    FixturePathAuthorityV1,
    StationReceiverTopologyV1,
)
from leo.station.geometry import (
    CaptureReceiverGeometryBindingV1,
    StationReceiverGeometryV1,
)
from leo.station.pinned_loader import StationAuthorityReader


@dataclass(frozen=True, slots=True)
class AuthorityFileReference:
    relative_path: str
    file_digest: str


@dataclass(frozen=True, slots=True)
class FixtureAuthorityFileReference:
    manifest_digest: str
    relative_path: str
    file_digest: str


@dataclass(frozen=True, slots=True)
class ResolvedCaptureAuthority:
    topology: StationReceiverTopologyV1 | None
    path_authority: CaptureHardwareBindingV1 | FixturePathAuthorityV1
    geometry: StationReceiverGeometryV1 | None = None
    geometry_binding: CaptureReceiverGeometryBindingV1 | None = None


class UnreviewedTestFixtureAuthorityError(ValueError):
    """The TEST bundle is not part of the reviewed digest-pinned corpus."""


class PinnedCaptureAuthorityResolver:
    """Resolve LIVE/IMPORT through topology and reviewed TEST through exact files."""

    def __init__(
        self,
        reader: StationAuthorityReader,
        *,
        topology: AuthorityFileReference,
        geometry: AuthorityFileReference | None = None,
        fixtures: tuple[FixtureAuthorityFileReference, ...] = (),
    ) -> None:
        manifests = tuple(item.manifest_digest for item in fixtures)
        if len(set(manifests)) != len(manifests):
            raise ValueError("fixture authority manifest digests must be unique")
        self._reader = reader
        self._topology = topology
        self._geometry = geometry
        self._fixtures = {item.manifest_digest: item for item in fixtures}

    def resolve(
        self,
        manifest: RecordingManifestV1,
        *,
        observed_manifest_file_digest: str,
    ) -> ResolvedCaptureAuthority:
        if manifest.source_type is SourceType.TEST:
            reference = self._fixtures.get(observed_manifest_file_digest)
            if reference is None:
                raise UnreviewedTestFixtureAuthorityError(
                    "TEST manifest has no reviewed digest-pinned fixture authority"
                )
            authority = self._reader.read_fixture_authority(
                reference.relative_path,
                expected_file_digest=reference.file_digest,
            )
            expected = FixturePathAuthorityV1.create(
                manifest,
                observed_manifest_file_digest=observed_manifest_file_digest,
            )
            if authority != expected:
                raise ValueError("fixture authority differs from the verified TEST manifest")
            return ResolvedCaptureAuthority(topology=None, path_authority=authority)
        topology = self._reader.read_topology(
            self._topology.relative_path,
            expected_file_digest=self._topology.file_digest,
        )
        path_authority = CaptureHardwareBindingV1.create(
            manifest,
            observed_manifest_file_digest=observed_manifest_file_digest,
            topology=topology,
        )
        geometry = None
        geometry_binding = None
        if self._geometry is not None:
            geometry = self._reader.read_geometry(
                self._geometry.relative_path,
                expected_file_digest=self._geometry.file_digest,
            )
            geometry_binding = CaptureReceiverGeometryBindingV1.create(
                path_authority,
                geometry=geometry,
            )
        return ResolvedCaptureAuthority(
            topology=topology,
            path_authority=path_authority,
            geometry=geometry,
            geometry_binding=geometry_binding,
        )
