from __future__ import annotations

import pytest
from pydantic import ValidationError

from leo.contracts.digests import canonical_json_bytes
from leo.station.authority import (
    CaptureHardwareBindingV1,
    CaptureHardwareBindingV2,
    VerifiedRecordingManifestSnapshotV1,
    VerifiedRecordingManifestSnapshotV2,
    parse_capture_hardware_binding,
    parse_capture_hardware_binding_json,
)

from .manifest_examples import (
    manifest_example,
    manifest_example_v2,
    topology_for_manifest,
    verified_digest,
)


def test_versioned_station_parser_preserves_the_v1_contract() -> None:
    manifest = manifest_example(
        radio_count=1,
        applied_receiver_ids=(0, 1),
    )
    binding = CaptureHardwareBindingV1.create(
        manifest,
        observed_manifest_file_digest=verified_digest(manifest),
        topology=topology_for_manifest(manifest),
    )

    parsed = parse_capture_hardware_binding(binding.model_dump(mode="json"))

    assert type(parsed) is CaptureHardwareBindingV1
    assert parsed == binding


def test_v2_snapshot_preserves_the_complete_digest_bound_manifest() -> None:
    manifest = manifest_example_v2(radio_count=1, applied_receiver_ids=(0, 1))
    digest = verified_digest(manifest)

    with pytest.raises(ValidationError, match="snapshot digest does not match content"):
        VerifiedRecordingManifestSnapshotV1.from_verified_manifest(
            manifest,
            observed_manifest_file_digest=digest,
        )

    snapshot = VerifiedRecordingManifestSnapshotV2.from_verified_manifest(
        manifest,
        observed_manifest_file_digest=digest,
    )
    persisted_manifest = snapshot.model_dump(mode="json")["recording_manifest"]

    assert snapshot.manifest_digest == digest
    assert snapshot.recording_manifest == manifest
    assert persisted_manifest == manifest.model_dump(mode="json")
    assert persisted_manifest["capture_plan"]["profile_revision"]["profile"]["kernel_buffers"] == 8
    assert persisted_manifest["streams"][0]["continuity"]["queue_capacity_refills"] == 32


def test_v2_binding_round_trips_through_the_versioned_station_parser() -> None:
    manifest = manifest_example_v2(radio_count=2, applied_receiver_ids=(0, 1))
    binding = CaptureHardwareBindingV2.create(
        manifest,
        observed_manifest_file_digest=verified_digest(manifest),
        topology=topology_for_manifest(manifest),
    )

    parsed = parse_capture_hardware_binding(binding.model_dump(mode="json"))
    parsed_json = parse_capture_hardware_binding_json(
        canonical_json_bytes(binding.model_dump(mode="json"))
    )

    assert isinstance(parsed, CaptureHardwareBindingV2)
    assert isinstance(parsed_json, CaptureHardwareBindingV2)
    assert parsed == binding
    assert parsed_json == binding
    assert len(binding.paths) == 4


def test_v2_binding_rejects_a_v2_only_manifest_field_retarget() -> None:
    manifest = manifest_example_v2(radio_count=1, applied_receiver_ids=(0, 1))
    binding = CaptureHardwareBindingV2.create(
        manifest,
        observed_manifest_file_digest=verified_digest(manifest),
        topology=topology_for_manifest(manifest),
    )
    document = binding.model_dump(mode="json")
    profile = document["verified_manifest_snapshot"]["recording_manifest"]["capture_plan"][
        "profile_revision"
    ]["profile"]
    profile["kernel_buffers"] = 16

    with pytest.raises(ValidationError, match="digest does not match content"):
        CaptureHardwareBindingV2.model_validate(document)
