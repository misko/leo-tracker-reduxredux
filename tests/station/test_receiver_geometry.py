from __future__ import annotations

import hashlib
import math
import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from leo.contracts.digests import canonical_json_bytes, sha256_digest
from leo.contracts.states import SourceType
from leo.station.geometry import (
    CaptureReceiverGeometryBindingV1,
    CartesianVectorMetersV1,
    RadioReceiverGeometryV1,
    ReceiverFixtureDefinitionV1,
    ReceiverFixtureSlotV1,
    ReceiverSlotAssignmentV1,
    StationReceiverGeometryV1,
    UnitVectorV1,
)
from leo.station.pinned_loader import (
    PinnedAuthorityJsonLoader,
    PinnedStationAuthorityReader,
    require_owner_uid,
)
from leo.station.resolver import AuthorityFileReference, PinnedCaptureAuthorityResolver

from .manifest_examples import manifest_example, topology_for_manifest, verified_digest

_DESIGN_DIGEST = f"sha256:{'1' * 64}"
_MESH_DIGEST = f"sha256:{'2' * 64}"
_REPOSITORY = Path(__file__).resolve().parents[2]
_DEPLOYED_GEOMETRY_FILE_DIGEST = (
    "sha256:758262ecc67044065e2e2facc46f2cc77997883eabf0f7f1a4c5fa761fba65f7"
)


def _fixture() -> ReceiverFixtureDefinitionV1:
    sine = math.sin(math.radians(10.0))
    cosine = math.cos(math.radians(10.0))
    return ReceiverFixtureDefinitionV1.create(
        fixture_part_id="LT3D-001A",
        geometry_revision="lt3d-001a-nominal-v1",
        slots=(
            ReceiverFixtureSlotV1(
                slot_id="positive-x",
                mount_reference_position_m=CartesianVectorMetersV1(x=0.04, y=0.0, z=0.076),
                mount_axis_unit=UnitVectorV1(x=sine, y=0.0, z=cosine),
            ),
            ReceiverFixtureSlotV1(
                slot_id="negative-x",
                mount_reference_position_m=CartesianVectorMetersV1(x=-0.04, y=0.0, z=0.076),
                mount_axis_unit=UnitVectorV1(x=-sine, y=0.0, z=cosine),
            ),
        ),
        design_uri="3d_prints/LT3D-001-dual-lnbf-stand/DESIGN.md",
        design_sha256=_DESIGN_DIGEST,
        mesh_uri="3d_prints/LT3D-001-dual-lnbf-stand/LT3D-001A-dual-lnbf-stand.stl",
        mesh_sha256=_MESH_DIGEST,
    )


def _hardware_binding():
    from leo.station.authority import CaptureHardwareBindingV1

    manifest = manifest_example(
        radio_count=1,
        applied_receiver_ids=(0, 1),
        source_type=SourceType.IMPORT,
    )
    return CaptureHardwareBindingV1.create(
        manifest,
        observed_manifest_file_digest=verified_digest(manifest),
        topology=topology_for_manifest(manifest),
    )


def _geometry(binding=None):
    binding = binding or _hardware_binding()
    first, second = binding.paths
    fixture = _fixture()
    radio = RadioReceiverGeometryV1(
        radio_id=first.radio_id,
        radio_serial=first.radio_serial,
        fixture_part_id=fixture.fixture_part_id,
        fixture_digest=fixture.fixture_digest,
        assignments=(
            ReceiverSlotAssignmentV1(
                receiver_id=first.receiver_id,
                physical_receiver_id=first.physical_receiver_id,
                slot_id="negative-x",
                mapping_status="verified",
                mapping_evidence="bench cable trace 2026-09-20",
            ),
            ReceiverSlotAssignmentV1(
                receiver_id=second.receiver_id,
                physical_receiver_id=second.physical_receiver_id,
                slot_id="positive-x",
                mapping_status="verified",
                mapping_evidence="bench cable trace 2026-09-20",
            ),
        ),
    )
    return StationReceiverGeometryV1.create(
        station_id=binding.station_id,
        geometry_revision="station-geometry-v1",
        valid_from_utc_ns=0,
        valid_until_utc_ns=9_223_372_036_854_775_807,
        fixtures=(fixture,),
        radios=(radio,),
    )


def test_lt3d_fixture_records_exact_baseline_and_boresight_geometry() -> None:
    fixture = _fixture()

    assert tuple(item.slot_id for item in fixture.slots) == ("negative-x", "positive-x")
    assert fixture.fixture_digest.startswith("sha256:")
    baseline_m = (
        fixture.slots[1].mount_reference_position_m.x
        - fixture.slots[0].mount_reference_position_m.x
    )
    assert baseline_m == pytest.approx(0.08)
    dot = sum(
        getattr(fixture.slots[0].mount_axis_unit, axis)
        * getattr(fixture.slots[1].mount_axis_unit, axis)
        for axis in ("x", "y", "z")
    )
    assert math.degrees(math.acos(dot)) == pytest.approx(20.0)
    assert all(item.rf_phase_center_position_m is None for item in fixture.slots)
    assert all(item.rf_boresight_unit is None for item in fixture.slots)


def test_station_geometry_and_capture_binding_are_content_addressed() -> None:
    hardware = _hardware_binding()
    geometry = _geometry()

    captured = CaptureReceiverGeometryBindingV1.create(hardware, geometry=geometry)

    assert captured.hardware_binding_digest == hardware.binding_digest
    assert captured.station_geometry_digest == geometry.geometry_digest
    assert tuple(item.receiver_id for item in captured.paths) == (0, 1)
    assert tuple(item.slot_id for item in captured.paths) == ("negative-x", "positive-x")
    assert all(item.mapping_status == "verified" for item in captured.paths)
    assert CaptureReceiverGeometryBindingV1.model_validate(
        captured.model_dump(mode="json")
    ) == captured


def test_geometry_rejects_forged_digest_and_non_unit_boresight() -> None:
    fixture = _fixture()
    forged = fixture.model_dump(mode="python")
    forged["fixture_digest"] = f"sha256:{'f' * 64}"
    with pytest.raises(ValidationError, match="fixture digest"):
        ReceiverFixtureDefinitionV1.model_validate(forged)

    with pytest.raises(ValidationError, match="unit length"):
        UnitVectorV1(x=0.0, y=0.0, z=0.5)


def test_capture_binding_rejects_unmapped_physical_receiver() -> None:
    hardware = _hardware_binding()
    document = _geometry().model_dump(mode="python")
    document.pop("geometry_digest")
    document["radios"][0]["assignments"][0]["physical_receiver_id"] = "other-path"
    geometry = StationReceiverGeometryV1.create(
        station_id=document["station_id"],
        geometry_revision=document["geometry_revision"],
        valid_from_utc_ns=document["valid_from_utc_ns"],
        valid_until_utc_ns=document["valid_until_utc_ns"],
        fixtures=tuple(
            ReceiverFixtureDefinitionV1.model_validate(item) for item in document["fixtures"]
        ),
        radios=tuple(RadioReceiverGeometryV1.model_validate(item) for item in document["radios"]),
    )

    with pytest.raises(ValueError, match="physical path"):
        CaptureReceiverGeometryBindingV1.create(hardware, geometry=geometry)


def test_deployed_r21_lt3d_geometry_matches_released_design_evidence() -> None:
    authority_path = (
        _REPOSITORY / "deploy/station/gauss-r21-lt3d-001a-20260920-v1.json"
    )
    payload = authority_path.read_bytes()
    assert sha256_digest(payload) == _DEPLOYED_GEOMETRY_FILE_DIGEST
    authority = StationReceiverGeometryV1.model_validate_json(payload)
    fixture = authority.fixtures[0]

    assert authority.radios[0].radio_serial == "10400056f695001322002d0010ad1719f2"
    assert fixture.fixture_part_id == "LT3D-001A"
    assert all(
        item.mapping_status == "provisional" for item in authority.radios[0].assignments
    )
    for relative_path, expected_digest in (
        (fixture.design_uri, fixture.design_sha256),
        (fixture.mesh_uri, fixture.mesh_sha256),
    ):
        digest = hashlib.sha256((_REPOSITORY / relative_path).read_bytes()).hexdigest()
        assert f"sha256:{digest}" == expected_digest


def test_pinned_resolver_logs_geometry_bound_to_the_verified_capture(tmp_path: Path) -> None:
    from leo.station.authority import CaptureHardwareBindingV1

    manifest = manifest_example(
        radio_count=1,
        applied_receiver_ids=(0, 1),
        source_type=SourceType.IMPORT,
    )
    topology = topology_for_manifest(manifest)
    hardware = CaptureHardwareBindingV1.create(
        manifest,
        observed_manifest_file_digest=verified_digest(manifest),
        topology=topology,
    )
    geometry = _geometry(hardware)
    root = tmp_path / "authority"
    root.mkdir(mode=0o750)

    def publish(name: str, document: object) -> str:
        payload = canonical_json_bytes(document)
        path = root / name
        path.write_bytes(payload)
        path.chmod(0o440)
        return sha256_digest(payload)

    topology_digest = publish("topology.json", topology.model_dump(mode="json"))
    geometry_digest = publish("geometry.json", geometry.model_dump(mode="json"))
    loader = PinnedAuthorityJsonLoader(
        root,
        ownership_validator=require_owner_uid(os.getuid()),
    )
    try:
        resolver = PinnedCaptureAuthorityResolver(
            PinnedStationAuthorityReader(loader),
            topology=AuthorityFileReference("topology.json", topology_digest),
            geometry=AuthorityFileReference("geometry.json", geometry_digest),
        )
        resolved = resolver.resolve(
            manifest,
            observed_manifest_file_digest=verified_digest(manifest),
        )
    finally:
        loader.close()

    assert resolved.geometry == geometry
    assert resolved.geometry_binding is not None
    assert resolved.geometry_binding.hardware_binding_digest == hardware.binding_digest
