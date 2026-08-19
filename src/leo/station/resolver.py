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


class PinnedCaptureAuthorityResolver:
    """Resolve LIVE/IMPORT through topology and reviewed TEST through exact files."""

    def __init__(
        self,
        reader: StationAuthorityReader,
        *,
        topology: AuthorityFileReference,
        fixtures: tuple[FixtureAuthorityFileReference, ...] = (),
    ) -> None:
        manifests = tuple(item.manifest_digest for item in fixtures)
        if len(set(manifests)) != len(manifests):
            raise ValueError("fixture authority manifest digests must be unique")
        self._reader = reader
        self._topology = topology
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
                raise ValueError("TEST manifest has no reviewed digest-pinned fixture authority")
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
        return ResolvedCaptureAuthority(
            topology=topology,
            path_authority=CaptureHardwareBindingV1.create(
                manifest,
                observed_manifest_file_digest=observed_manifest_file_digest,
                topology=topology,
            ),
        )
