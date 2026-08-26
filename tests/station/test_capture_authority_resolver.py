from __future__ import annotations

import os
from pathlib import Path

import pytest

from leo.contracts.digests import canonical_json_bytes, sha256_digest
from leo.contracts.states import SourceType
from leo.station.authority import (
    CaptureHardwareBindingV1,
    CaptureHardwareBindingV2,
    CaptureHardwareBindingV3,
    FixturePathAuthorityV1,
    StationReceiverTopologyV1,
)
from leo.station.pinned_loader import (
    PinnedAuthorityJsonLoader,
    PinnedStationAuthorityReader,
    require_owner_uid,
)
from leo.station.resolver import (
    AuthorityFileReference,
    FixtureAuthorityFileReference,
    PinnedCaptureAuthorityResolver,
)

from .manifest_examples import (
    manifest_example,
    manifest_example_v2,
    manifest_example_v3,
    topology_for_manifest,
    verified_digest,
)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_GAUSS_TOPOLOGY_FILE_DIGEST = (
    "sha256:5ec14f15bfe2a6abc52024f41db29b4ab6123209e6c4779a47644b1e70c477ae"
)


def _publish(root: Path, relative_path: str, document: object) -> str:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    root.chmod(0o750)
    path.parent.chmod(0o750)
    payload = canonical_json_bytes(document)
    path.write_bytes(payload)
    path.chmod(0o440)
    return sha256_digest(payload)


def _loader(root: Path) -> PinnedAuthorityJsonLoader:
    return PinnedAuthorityJsonLoader(
        root,
        ownership_validator=require_owner_uid(os.getuid()),
    )


def test_live_and_import_authority_is_derived_from_the_pinned_topology(
    tmp_path: Path,
) -> None:
    root = tmp_path / "authority"
    root.mkdir()
    manifest = manifest_example(
        radio_count=2,
        applied_receiver_ids=(0, 1),
        source_type=SourceType.IMPORT,
    )
    topology = topology_for_manifest(manifest)
    topology_file_digest = _publish(
        root,
        "station/topology.json",
        topology.model_dump(mode="json"),
    )
    loader = _loader(root)
    try:
        resolver = PinnedCaptureAuthorityResolver(
            PinnedStationAuthorityReader(loader),
            topology=AuthorityFileReference(
                relative_path="station/topology.json",
                file_digest=topology_file_digest,
            ),
        )
        resolved = resolver.resolve(
            manifest,
            observed_manifest_file_digest=verified_digest(manifest),
        )
    finally:
        loader.close()

    assert resolved.topology == topology
    assert isinstance(resolved.path_authority, CaptureHardwareBindingV1)
    assert len(resolved.path_authority.paths) == 4


def test_v2_import_authority_uses_the_v2_manifest_binding(tmp_path: Path) -> None:
    root = tmp_path / "authority"
    root.mkdir()
    manifest = manifest_example_v2(
        radio_count=1,
        applied_receiver_ids=(0, 1),
        source_type=SourceType.IMPORT,
    )
    topology = topology_for_manifest(manifest)
    topology_file_digest = _publish(
        root,
        "station/topology.json",
        topology.model_dump(mode="json"),
    )
    loader = _loader(root)
    try:
        resolver = PinnedCaptureAuthorityResolver(
            PinnedStationAuthorityReader(loader),
            topology=AuthorityFileReference(
                relative_path="station/topology.json",
                file_digest=topology_file_digest,
            ),
        )
        resolved = resolver.resolve(
            manifest,
            observed_manifest_file_digest=verified_digest(manifest),
        )
    finally:
        loader.close()

    assert resolved.topology == topology
    assert isinstance(resolved.path_authority, CaptureHardwareBindingV2)
    assert resolved.path_authority.verified_manifest_snapshot.recording_manifest.model_dump(
        mode="json"
    ) == manifest.model_dump(mode="json")


def test_v3_import_authority_uses_the_device_axis_manifest_binding(tmp_path: Path) -> None:
    root = tmp_path / "authority"
    root.mkdir()
    manifest = manifest_example_v3(
        radio_count=1,
        applied_receiver_ids=(0, 1),
        source_type=SourceType.IMPORT,
    )
    topology = topology_for_manifest(manifest)
    topology_file_digest = _publish(
        root,
        "station/topology.json",
        topology.model_dump(mode="json"),
    )
    loader = _loader(root)
    try:
        resolver = PinnedCaptureAuthorityResolver(
            PinnedStationAuthorityReader(loader),
            topology=AuthorityFileReference(
                relative_path="station/topology.json",
                file_digest=topology_file_digest,
            ),
        )
        resolved = resolver.resolve(
            manifest,
            observed_manifest_file_digest=verified_digest(manifest),
        )
    finally:
        loader.close()

    assert resolved.topology == topology
    assert isinstance(resolved.path_authority, CaptureHardwareBindingV3)
    assert resolved.path_authority.verified_manifest_snapshot.recording_manifest == manifest


def test_deployed_gauss_four_path_authority_has_the_reviewed_pinned_digest() -> None:
    path = _PROJECT_ROOT / "deploy/station/gauss-four-path-postreboot-20260816-v1.json"
    payload = path.read_bytes()
    assert sha256_digest(payload) == _GAUSS_TOPOLOGY_FILE_DIGEST
    topology = StationReceiverTopologyV1.model_validate_json(payload)
    assert topology.topology_digest == (
        "sha256:1aacfb9c5904b6524cad2e82b52427ba0d884ec8c391af58e6d2f5c92c770431"
    )
    assert {
        (radio.radio_id, assignment.receiver_id, assignment.physical_receiver_id)
        for radio in topology.radios
        for assignment in radio.receiver_assignments
    } == {
        ("radio_pluto_5d4d", 0, "rx_lnb_a"),
        ("radio_pluto_5d4d", 1, "rx_lnb_b"),
        ("radio_pluto_19f2", 0, "rx_lnb_c"),
        ("radio_pluto_19f2", 1, "rx_lnb_d"),
    }
    assert {radio.endpoint_evidence.evidence_digest for radio in topology.radios} == {
        "sha256:056df424372076bf2f4e3b341ce97f264765de08b949ab72c95b5bc92decf476",
        "sha256:c518ed50a60ca3117bbae1c8fe7d33d702f50f9458f0779a33116f43696590f2",
    }


def test_test_authority_requires_an_exact_reviewed_manifest_digest_mapping(
    tmp_path: Path,
) -> None:
    root = tmp_path / "authority"
    root.mkdir()
    manifest = manifest_example(radio_count=1, applied_receiver_ids=(0, 1))
    topology = topology_for_manifest(manifest)
    fixture = FixturePathAuthorityV1.create(
        manifest,
        observed_manifest_file_digest=verified_digest(manifest),
    )
    topology_file_digest = _publish(
        root,
        "station/topology.json",
        topology.model_dump(mode="json"),
    )
    fixture_file_digest = _publish(
        root,
        "fixtures/trial.json",
        fixture.model_dump(mode="json"),
    )
    loader = _loader(root)
    try:
        reader = PinnedStationAuthorityReader(loader)
        without_fixture = PinnedCaptureAuthorityResolver(
            reader,
            topology=AuthorityFileReference(
                relative_path="station/topology.json",
                file_digest=topology_file_digest,
            ),
        )
        with pytest.raises(ValueError, match="no reviewed digest-pinned fixture"):
            without_fixture.resolve(
                manifest,
                observed_manifest_file_digest=verified_digest(manifest),
            )
        resolver = PinnedCaptureAuthorityResolver(
            reader,
            topology=AuthorityFileReference(
                relative_path="station/topology.json",
                file_digest=topology_file_digest,
            ),
            fixtures=(
                FixtureAuthorityFileReference(
                    manifest_digest=verified_digest(manifest),
                    relative_path="fixtures/trial.json",
                    file_digest=fixture_file_digest,
                ),
            ),
        )
        resolved = resolver.resolve(
            manifest,
            observed_manifest_file_digest=verified_digest(manifest),
        )
    finally:
        loader.close()

    assert resolved.topology is None
    assert resolved.path_authority == fixture
