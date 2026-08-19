from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from leo.contracts.digests import canonical_digest, canonical_json_bytes
from leo.contracts.states import RadioTransport, SourceType
from leo.station.authority import (
    CaptureHardwareBindingV1,
    FixturePathAuthorityV1,
    RadioEndpointEvidenceV1,
    StationRadioTopologyV1,
    StationReceiverAssignmentV1,
    StationReceiverTopologyV1,
    VerifiedRecordingManifestSnapshotV1,
)

from .manifest_examples import manifest_example, topology_for_manifest, verified_digest

_DIGEST_A = f"sha256:{'1' * 64}"
_DIGEST_B = f"sha256:{'2' * 64}"


def _assignment(
    receiver_id: int,
    *,
    radio: str = "a",
    start: int = 1_000,
    end: int = 2_000,
    epoch: str | None = None,
) -> StationReceiverAssignmentV1:
    return StationReceiverAssignmentV1(
        receiver_id=receiver_id,
        physical_receiver_id=f"physical-{radio}-rx{receiver_id}",
        hardware_epoch_external_id=epoch or f"hardware-{radio}-rx{receiver_id}-v1",
        valid_from_utc_ns=start,
        valid_until_utc_ns=end,
    )


def _radio(
    name: str,
    *,
    assignments: tuple[StationReceiverAssignmentV1, ...] | None = None,
    endpoint: str | None = None,
    evidence_digest: str = _DIGEST_A,
) -> StationRadioTopologyV1:
    return StationRadioTopologyV1.create(
        radio_id=f"radio-{name}",
        radio_serial=f"serial-{name}",
        endpoint_evidence=RadioEndpointEvidenceV1(
            transport=RadioTransport.IIO_IP,
            endpoint=endpoint or f"ip:192.0.2.{10 + ord(name) - ord('a')}",
            evidence_uri=f"authority/radio-{name}.json",
            evidence_digest=evidence_digest,
        ),
        receiver_assignments=assignments
        or (_assignment(0, radio=name), _assignment(1, radio=name)),
    )


def _topology(*radios: StationRadioTopologyV1) -> StationReceiverTopologyV1:
    return StationReceiverTopologyV1.create(
        station_id="station-gauss",
        topology_revision="gauss-receiver-map-v1",
        valid_from_utc_ns=1_000,
        valid_until_utc_ns=2_000,
        radios=radios or (_radio("a"),),
    )


def _binding() -> CaptureHardwareBindingV1:
    manifest = manifest_example(radio_count=1, applied_receiver_ids=(0, 1))
    return CaptureHardwareBindingV1.create(
        manifest,
        observed_manifest_file_digest=verified_digest(manifest),
        topology=topology_for_manifest(manifest),
    )


def test_topology_factory_canonicalizes_complete_inventory_and_digest() -> None:
    topology = _topology(_radio("b"), _radio("a"))

    assert tuple(item.radio_id for item in topology.radios) == ("radio-a", "radio-b")
    assert tuple(
        item.receiver_id for item in topology.radios[0].receiver_assignments
    ) == (0, 1)
    assert topology.topology_digest.startswith("sha256:")
    assert StationReceiverTopologyV1.model_validate(topology.model_dump(mode="json")) == topology


def test_topology_rejects_noncanonical_radio_and_assignment_order() -> None:
    radio = _radio("a")
    reversed_radio = radio.model_dump(mode="python")
    reversed_radio["receiver_assignments"] = tuple(
        reversed(reversed_radio["receiver_assignments"])
    )
    with pytest.raises(ValidationError, match="canonical receiver/time order"):
        StationRadioTopologyV1.model_validate(reversed_radio)

    topology = _topology(_radio("a"), _radio("b"))
    reversed_topology = topology.model_dump(mode="python")
    reversed_topology["radios"] = tuple(reversed(reversed_topology["radios"]))
    with pytest.raises(ValidationError, match="canonical identity order"):
        StationReceiverTopologyV1.model_validate(reversed_topology)


def test_topology_rejects_partial_radio_inventory() -> None:
    with pytest.raises(ValidationError, match="cannot omit RX0 or RX1"):
        _radio("a", assignments=(_assignment(0),))


def test_topology_rejects_overlapping_gapped_and_inexact_intervals() -> None:
    overlap = (
        _assignment(0, start=1_000, end=1_600, epoch="epoch-0a"),
        _assignment(0, start=1_500, end=2_000, epoch="epoch-0b"),
        _assignment(1),
    )
    with pytest.raises(ValidationError, match="overlap"):
        _radio("a", assignments=overlap)

    gap = (
        _assignment(0, start=1_000, end=1_400, epoch="epoch-0a"),
        _assignment(0, start=1_500, end=2_000, epoch="epoch-0b"),
        _assignment(1),
    )
    with pytest.raises(ValidationError, match="exactly contiguous"):
        _topology(_radio("a", assignments=gap))

    short = (_assignment(0, start=1_100), _assignment(1))
    with pytest.raises(ValidationError, match="full topology interval"):
        _topology(_radio("a", assignments=short))


@pytest.mark.parametrize(
    "mutate",
    [
        lambda document: document["radios"][0].__setitem__("radio_serial", "forged"),
        lambda document: document["radios"][0]["endpoint_evidence"].__setitem__(
            "endpoint", "ip:203.0.113.99"
        ),
        lambda document: document["radios"][0]["receiver_assignments"][0].__setitem__(
            "physical_receiver_id", "forged-path"
        ),
        lambda document: document["radios"][0]["receiver_assignments"][0].__setitem__(
            "hardware_epoch_external_id", "forged-epoch"
        ),
    ],
)
def test_topology_content_digest_rejects_identity_forgery(
    mutate: Any,
) -> None:
    document = _topology(_radio("a")).model_dump(mode="python")
    mutate(document)

    with pytest.raises(ValidationError, match="digest does not match content"):
        StationReceiverTopologyV1.model_validate(document)


def test_topology_rejects_duplicate_inventory_identities() -> None:
    first = _radio("a")
    duplicate = StationRadioTopologyV1.create(
        radio_id="radio-b",
        radio_serial=first.radio_serial,
        endpoint_evidence=first.endpoint_evidence,
        receiver_assignments=(
            _assignment(0, radio="b"),
            _assignment(1, radio="b"),
        ),
    )
    with pytest.raises(ValidationError, match="serials must be unique"):
        _topology(first, duplicate)


def test_capture_binding_resolves_exact_paths_and_rejects_retargeted_authority() -> None:
    manifest = manifest_example(radio_count=1, applied_receiver_ids=(0, 1))
    topology = topology_for_manifest(manifest)
    binding = CaptureHardwareBindingV1.create(
        manifest,
        observed_manifest_file_digest=verified_digest(manifest),
        topology=topology,
    )

    assert tuple(item.receiver_id for item in binding.paths) == (0, 1)
    assert binding.paths[0].physical_receiver_id == "physical-radio-0-rx0"
    assert binding.paths[0].hardware_epoch_external_id == "hardware-radio-0-rx0-v1"
    binding.assert_matches_topology(topology)

    radio = topology.radios[0]
    retargeted_radio = StationRadioTopologyV1.create(
        radio_id=radio.radio_id,
        radio_serial=radio.radio_serial,
        endpoint_evidence=RadioEndpointEvidenceV1(
            transport=radio.endpoint_evidence.transport,
            endpoint="ip:203.0.113.44",
            evidence_uri=radio.endpoint_evidence.evidence_uri,
            evidence_digest=radio.endpoint_evidence.evidence_digest,
        ),
        receiver_assignments=radio.receiver_assignments,
    )
    retargeted = StationReceiverTopologyV1.create(
        station_id=topology.station_id,
        topology_revision=topology.topology_revision,
        valid_from_utc_ns=topology.valid_from_utc_ns,
        valid_until_utc_ns=topology.valid_until_utc_ns,
        radios=(retargeted_radio,),
    )
    assert retargeted.topology_digest != topology.topology_digest
    with pytest.raises(ValueError, match="retargeted"):
        binding.assert_matches_topology(retargeted)


def test_capture_binding_rejects_serial_forgery_and_epoch_boundary_crossing() -> None:
    manifest = manifest_example(radio_count=1, applied_receiver_ids=(0,))
    canonical_topology = topology_for_manifest(manifest)
    canonical_radio = canonical_topology.radios[0]
    wrong_serial_radio = StationRadioTopologyV1.create(
        radio_id=canonical_radio.radio_id,
        radio_serial="forged-serial",
        endpoint_evidence=canonical_radio.endpoint_evidence,
        receiver_assignments=canonical_radio.receiver_assignments,
    )
    with pytest.raises(ValueError, match="ID/serial"):
        CaptureHardwareBindingV1.create(
            manifest,
            observed_manifest_file_digest=verified_digest(manifest),
            topology=StationReceiverTopologyV1.create(
                station_id=canonical_topology.station_id,
                topology_revision=canonical_topology.topology_revision,
                valid_from_utc_ns=canonical_topology.valid_from_utc_ns,
                valid_until_utc_ns=canonical_topology.valid_until_utc_ns,
                radios=(wrong_serial_radio,),
            ),
        )

    split = 100_500
    crossing_radio = StationRadioTopologyV1.create(
        radio_id=canonical_radio.radio_id,
        radio_serial=canonical_radio.radio_serial,
        endpoint_evidence=canonical_radio.endpoint_evidence,
        receiver_assignments=(
            StationReceiverAssignmentV1(
                receiver_id=0,
                physical_receiver_id="physical-radio-0-rx0",
                hardware_epoch_external_id="epoch-0a",
                valid_from_utc_ns=0,
                valid_until_utc_ns=split,
            ),
            StationReceiverAssignmentV1(
                receiver_id=0,
                physical_receiver_id="physical-radio-0-rx0",
                hardware_epoch_external_id="epoch-0b",
                valid_from_utc_ns=split,
                valid_until_utc_ns=1_000_000,
            ),
            StationReceiverAssignmentV1(
                receiver_id=1,
                physical_receiver_id="physical-radio-0-rx1",
                hardware_epoch_external_id="epoch-1",
                valid_from_utc_ns=0,
                valid_until_utc_ns=1_000_000,
            ),
        ),
    )
    with pytest.raises(ValueError, match="crosses or lacks"):
        CaptureHardwareBindingV1.create(
            manifest,
            observed_manifest_file_digest=verified_digest(manifest),
            topology=StationReceiverTopologyV1.create(
                station_id=canonical_topology.station_id,
                topology_revision=canonical_topology.topology_revision,
                valid_from_utc_ns=0,
                valid_until_utc_ns=1_000_000,
                radios=(crossing_radio,),
            ),
        )


def test_capture_binding_digest_rejects_path_forgery() -> None:
    document = _binding().model_dump(mode="python")
    document["paths"][0]["physical_receiver_id"] = "forged-physical-path"

    with pytest.raises(ValidationError, match="digest does not match content"):
        CaptureHardwareBindingV1.model_validate(document)


@pytest.mark.parametrize(
    ("radio_count", "receiver_ids", "expected_paths"),
    [
        (1, (0,), 1),
        (1, (0, 1), 2),
        (2, (0,), 2),
        (2, (0, 1), 4),
    ],
    ids=("1r1rx", "1r2rx", "2r1rx", "2r2rx"),
)
def test_verified_manifest_inventory_matrix_is_exact_while_topology_is_complete(
    radio_count: int,
    receiver_ids: tuple[int, ...],
    expected_paths: int,
) -> None:
    manifest = manifest_example(
        radio_count=radio_count,
        applied_receiver_ids=receiver_ids,
    )
    topology = topology_for_manifest(manifest)
    snapshot = VerifiedRecordingManifestSnapshotV1.from_verified_manifest(
        manifest,
        observed_manifest_file_digest=verified_digest(manifest),
    )
    binding = CaptureHardwareBindingV1.create(
        manifest,
        observed_manifest_file_digest=verified_digest(manifest),
        topology=topology,
    )
    fixture = FixturePathAuthorityV1.create(
        manifest,
        observed_manifest_file_digest=verified_digest(manifest),
    )

    assert len(binding.paths) == expected_paths
    assert len(fixture.streams) == radio_count
    assert all(item.receiver_ids == receiver_ids for item in fixture.streams)
    assert snapshot.capture_start_utc_ns == min(
        item.capture_start_utc_ns for item in snapshot.streams
    )
    assert snapshot.capture_end_utc_ns == max(
        item.capture_end_utc_ns for item in snapshot.streams
    )
    assert all(
        {item.receiver_id for item in radio.receiver_assignments} == {0, 1}
        for radio in topology.radios
    )


def test_manifest_digest_retarget_is_rejected_before_inventory_narrowing() -> None:
    manifest = manifest_example(radio_count=1, applied_receiver_ids=(0, 1))
    original_digest = verified_digest(manifest)
    altered = manifest.model_dump(mode="python")
    altered["session_id"] = "retargeted-session"
    retargeted_manifest = type(manifest).model_validate(altered)

    with pytest.raises(ValueError, match="digest does not match canonical"):
        VerifiedRecordingManifestSnapshotV1.from_verified_manifest(
            retargeted_manifest,
            observed_manifest_file_digest=original_digest,
        )


def test_public_authority_builders_do_not_accept_caller_created_snapshots() -> None:
    manifest = manifest_example(radio_count=2, applied_receiver_ids=(0, 1))
    topology = topology_for_manifest(manifest)
    snapshot = VerifiedRecordingManifestSnapshotV1.from_verified_manifest(
        manifest,
        observed_manifest_file_digest=verified_digest(manifest),
    )
    capture_builder: Any = CaptureHardwareBindingV1.create
    fixture_builder: Any = FixturePathAuthorityV1.create

    with pytest.raises(TypeError, match="verified_manifest_snapshot"):
        capture_builder(verified_manifest_snapshot=snapshot, topology=topology)
    with pytest.raises(TypeError, match="verified_manifest_snapshot"):
        fixture_builder(verified_manifest_snapshot=snapshot)


def test_applied_inventory_never_falls_back_to_requested_receivers() -> None:
    manifest = manifest_example(
        radio_count=1,
        applied_receiver_ids=(0,),
        requested_receiver_ids=(0, 1),
    )
    snapshot = VerifiedRecordingManifestSnapshotV1.from_verified_manifest(
        manifest,
        observed_manifest_file_digest=verified_digest(manifest),
    )
    binding = CaptureHardwareBindingV1.create(
        manifest,
        observed_manifest_file_digest=verified_digest(manifest),
        topology=topology_for_manifest(manifest),
    )

    assert snapshot.streams[0].inventory_basis == "applied_settings"
    assert snapshot.streams[0].applied_receiver_ids == (0,)
    assert tuple(item.receiver_id for item in binding.paths) == (0,)


def test_verified_snapshot_rejects_requested_only_failed_stream_inventory() -> None:
    manifest = manifest_example(radio_count=2, applied_receiver_ids=(0, 1))
    failed_stream = manifest.streams[1].model_dump(mode="python")
    failed_stream.update(
        {
            "applied_settings": None,
            "state": "failed",
            "captured_sample_count": 0,
            "timing": None,
            "chunks": (),
            "timeline_relative_path": None,
            "timeline_sha256": None,
            "continuity": {
                "schema_version": 1,
                "refill_count": 0,
                "segment_count": 0,
            },
            "error": "transport failed before applied settings were observed",
        }
    )
    degraded = manifest.model_dump(mode="python")
    degraded["state"] = "degraded"
    degraded["streams"] = (manifest.streams[0].model_dump(mode="python"), failed_stream)
    degraded_manifest = type(manifest).model_validate(degraded)

    with pytest.raises(ValueError, match="requires applied settings"):
        VerifiedRecordingManifestSnapshotV1.from_verified_manifest(
            degraded_manifest,
            observed_manifest_file_digest=verified_digest(degraded_manifest),
        )


@pytest.mark.parametrize(
    "attack",
    ["omit-rx1", "invent-stream", "omit-stream", "extra-receiver", "duplicate-path"],
)
def test_capture_binding_rejects_manifest_inventory_omission_and_invention(
    attack: str,
) -> None:
    radio_count = 2 if attack == "omit-stream" else 1
    receiver_ids = (0,) if attack in {"invent-stream", "extra-receiver"} else (0, 1)
    manifest = manifest_example(
        radio_count=radio_count,
        applied_receiver_ids=receiver_ids,
    )
    binding = CaptureHardwareBindingV1.create(
        manifest,
        observed_manifest_file_digest=verified_digest(manifest),
        topology=topology_for_manifest(manifest),
    )
    document = binding.model_dump(mode="json")
    paths = document["paths"]
    if attack == "omit-rx1":
        document["paths"] = tuple(item for item in paths if item["receiver_id"] != 1)
    elif attack == "invent-stream":
        paths[0]["stream_id"] = "invented-stream"
    elif attack == "omit-stream":
        document["paths"] = tuple(
            item for item in paths if item["stream_id"] != "stream-1"
        )
    elif attack == "extra-receiver":
        assert len(paths) == 1
        invented = dict(paths[0])
        invented["receiver_id"] = 1
        invented["physical_receiver_id"] = "invented-extra-path"
        document["paths"] = (paths[0], invented)
    else:
        document["paths"] = (*paths, dict(paths[-1]))

    with pytest.raises(ValidationError, match="exactly equal every applied manifest path"):
        CaptureHardwareBindingV1.model_validate(document)


@pytest.mark.parametrize(
    ("field", "retarget"),
    [
        ("session_id", "invented-session"),
        ("manifest_digest", _DIGEST_A),
        ("capture_start_utc_ns", 1),
        ("capture_end_utc_ns", 999_999),
        ("manifest_snapshot_digest", _DIGEST_B),
    ],
)
def test_capture_binding_rejects_manifest_identity_or_interval_retarget(
    field: str,
    retarget: object,
) -> None:
    document = _binding().model_dump(mode="python")
    document[field] = retarget
    with pytest.raises(ValidationError, match="exactly match its verified manifest"):
        CaptureHardwareBindingV1.model_validate(document)


@pytest.mark.parametrize("serialized", [False, True], ids=("object", "json"))
def test_capture_binding_rejects_self_digested_two_radio_to_one_stream_snapshot(
    serialized: bool,
) -> None:
    manifest = manifest_example(radio_count=2, applied_receiver_ids=(0, 1))
    binding = CaptureHardwareBindingV1.create(
        manifest,
        observed_manifest_file_digest=verified_digest(manifest),
        topology=topology_for_manifest(manifest),
    )
    document = binding.model_dump(mode="json")
    forged_snapshot = document["verified_manifest_snapshot"]
    forged_snapshot["streams"] = forged_snapshot["streams"][:1]
    forged_snapshot["snapshot_digest"] = canonical_digest(
        {
            key: value
            for key, value in forged_snapshot.items()
            if key != "snapshot_digest"
        }
    )

    with pytest.raises(
        ValidationError,
        match="must contain every exact applied manifest stream",
    ):
        if serialized:
            CaptureHardwareBindingV1.model_validate_json(canonical_json_bytes(document))
        else:
            CaptureHardwareBindingV1(**document)  # type: ignore[arg-type]


def test_fixture_authority_is_structurally_evidence_only_and_unresolved() -> None:
    manifest = manifest_example(radio_count=2, applied_receiver_ids=(0, 1))
    authority = FixturePathAuthorityV1.create(
        manifest,
        observed_manifest_file_digest=verified_digest(manifest),
    )

    assert tuple(item.stream_id for item in authority.streams) == ("stream-0", "stream-1")
    assert authority.session_id == manifest.session_id
    assert authority.manifest_digest == verified_digest(manifest)
    assert authority.lineage_status == "unresolved"
    assert authority.evidence_only is True
    assert authority.current_analysis_eligible is False
    assert authority.physical_association_permitted is False
    assert authority.calibration_association_permitted is False
    assert authority.promotion_permitted is False
    assert "physical_receiver_id" not in authority.model_dump_json()
    assert "hardware_epoch" not in authority.model_dump_json()


@pytest.mark.parametrize(
    "field",
    [
        "current_analysis_eligible",
        "physical_association_permitted",
        "calibration_association_permitted",
        "promotion_permitted",
    ],
)
def test_fixture_authority_cannot_claim_current_or_association(field: str) -> None:
    manifest = manifest_example(radio_count=1, applied_receiver_ids=(0, 1))
    authority = FixturePathAuthorityV1.create(
        manifest,
        observed_manifest_file_digest=verified_digest(manifest),
    )
    document = authority.model_dump(mode="json")
    document[field] = True
    with pytest.raises(ValidationError):
        FixturePathAuthorityV1.model_validate(document)

    document = authority.model_dump(mode="python")
    document["physical_receiver_id"] = "invented-path"
    document["hardware_epoch_external_id"] = "invented-epoch"
    document["calibration_digest"] = _DIGEST_B
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        FixturePathAuthorityV1.model_validate(document)


def test_fixture_authority_rejects_stream_omission_and_non_test_manifest() -> None:
    manifest = manifest_example(radio_count=2, applied_receiver_ids=(0, 1))
    authority = FixturePathAuthorityV1.create(
        manifest,
        observed_manifest_file_digest=verified_digest(manifest),
    )
    document = authority.model_dump(mode="json")
    document["streams"] = document["streams"][:1]
    with pytest.raises(ValidationError, match="exactly equal every applied manifest"):
        FixturePathAuthorityV1.model_validate(document)

    live = manifest_example(
        radio_count=1,
        applied_receiver_ids=(0,),
        source_type=SourceType.LIVE,
    )
    with pytest.raises(ValueError, match="verified TEST manifest"):
        FixturePathAuthorityV1.create(
            live,
            observed_manifest_file_digest=verified_digest(live),
        )


@pytest.mark.parametrize("serialized", [False, True], ids=("object", "json"))
def test_fixture_rejects_self_digested_two_radio_to_one_stream_snapshot(
    serialized: bool,
) -> None:
    manifest = manifest_example(radio_count=2, applied_receiver_ids=(0, 1))
    authority = FixturePathAuthorityV1.create(
        manifest,
        observed_manifest_file_digest=verified_digest(manifest),
    )
    document = authority.model_dump(mode="json")
    forged_snapshot = document["verified_manifest_snapshot"]
    forged_snapshot["streams"] = forged_snapshot["streams"][:1]
    forged_snapshot["snapshot_digest"] = canonical_digest(
        {
            key: value
            for key, value in forged_snapshot.items()
            if key != "snapshot_digest"
        }
    )

    with pytest.raises(
        ValidationError,
        match="must contain every exact applied manifest stream",
    ):
        if serialized:
            FixturePathAuthorityV1.model_validate_json(canonical_json_bytes(document))
        else:
            FixturePathAuthorityV1(**document)  # type: ignore[arg-type]
