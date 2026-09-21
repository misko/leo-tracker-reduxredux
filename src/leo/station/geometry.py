"""Content-addressed receiver geometry and capture-time geometry bindings.

Geometry is a companion authority to :mod:`leo.station.authority`.  Keeping it
separate preserves the published recording and hardware-lineage contracts while
allowing analysis to opt into measured receiver positions and boresights.
"""

from __future__ import annotations

import math
from typing import Annotated, Literal, Self

from pydantic import Field, StringConstraints, field_validator, model_validator

from leo.contracts.base import ContractModel
from leo.contracts.digests import Sha256Digest, canonical_digest
from leo.contracts.recording import Identifier
from leo.station.authority import (
    CapturedHardwarePathV1,
    CaptureHardwareBindingV1,
    RadioSerial,
    UtcNs,
)

EvidenceUri = Annotated[str, StringConstraints(min_length=1, max_length=2048)]
_MAX_UTC_NS = 9_223_372_036_854_775_807


class CartesianVectorMetersV1(ContractModel):
    """One finite Cartesian vector expressed in metres."""

    schema_version: Literal[1] = 1
    x: Annotated[float, Field(ge=-100.0, le=100.0)]
    y: Annotated[float, Field(ge=-100.0, le=100.0)]
    z: Annotated[float, Field(ge=-100.0, le=100.0)]

    @model_validator(mode="after")
    def _finite(self) -> Self:
        if not all(math.isfinite(value) for value in (self.x, self.y, self.z)):
            raise ValueError("geometry vectors must be finite")
        return self


class UnitVectorV1(ContractModel):
    """One finite Cartesian direction with unit length."""

    schema_version: Literal[1] = 1
    x: Annotated[float, Field(ge=-1.0, le=1.0)]
    y: Annotated[float, Field(ge=-1.0, le=1.0)]
    z: Annotated[float, Field(ge=-1.0, le=1.0)]

    @model_validator(mode="after")
    def _unit_length(self) -> Self:
        values = (self.x, self.y, self.z)
        if not all(math.isfinite(value) for value in values):
            raise ValueError("geometry directions must be finite")
        if not math.isclose(math.sqrt(sum(value * value for value in values)), 1.0, abs_tol=1e-9):
            raise ValueError("geometry direction must have unit length")
        return self


class ReceiverFixtureSlotV1(ContractModel):
    """Mechanical pose for one receiver slot in fixture coordinates."""

    schema_version: Literal[1] = 1
    slot_id: Identifier
    mount_reference_position_m: CartesianVectorMetersV1
    mount_axis_unit: UnitVectorV1
    rf_phase_center_position_m: CartesianVectorMetersV1 | None = None
    rf_boresight_unit: UnitVectorV1 | None = None


def _slot_key(value: ReceiverFixtureSlotV1) -> str:
    return value.slot_id


class ReceiverFixtureDefinitionV1(ContractModel):
    """Immutable geometry supplied by one released mechanical fixture."""

    schema_version: Literal[1] = 1
    fixture_part_id: Identifier
    geometry_revision: Identifier
    coordinate_frame: Literal["fixture-local-right-front-up"] = (
        "fixture-local-right-front-up"
    )
    slots: Annotated[tuple[ReceiverFixtureSlotV1, ...], Field(min_length=2, max_length=2)]
    design_uri: EvidenceUri
    design_sha256: Sha256Digest
    mesh_uri: EvidenceUri
    mesh_sha256: Sha256Digest
    fixture_digest: Sha256Digest

    @field_validator("design_uri", "mesh_uri")
    @classmethod
    def _evidence_uri_is_plain(cls, value: str) -> str:
        if value != value.strip() or any(ord(character) < 0x20 for character in value):
            raise ValueError("geometry evidence URI must be trimmed plain text")
        return value

    @model_validator(mode="after")
    def _canonical_complete_slots_and_digest(self) -> Self:
        if tuple(sorted(self.slots, key=_slot_key)) != self.slots:
            raise ValueError("fixture slots must use canonical slot order")
        if len({slot.slot_id for slot in self.slots}) != len(self.slots):
            raise ValueError("fixture slot IDs must be unique")
        expected = receiver_fixture_digest(self)
        if self.fixture_digest != expected:
            raise ValueError(f"receiver fixture digest does not match content: {expected}")
        return self

    @classmethod
    def create(
        cls,
        *,
        fixture_part_id: str,
        geometry_revision: str,
        slots: tuple[ReceiverFixtureSlotV1, ...],
        design_uri: str,
        design_sha256: str,
        mesh_uri: str,
        mesh_sha256: str,
    ) -> ReceiverFixtureDefinitionV1:
        ordered = tuple(sorted(slots, key=_slot_key))
        values = {
            "schema_version": 1,
            "fixture_part_id": fixture_part_id,
            "geometry_revision": geometry_revision,
            "coordinate_frame": "fixture-local-right-front-up",
            "slots": tuple(item.model_dump(mode="json") for item in ordered),
            "design_uri": design_uri,
            "design_sha256": design_sha256,
            "mesh_uri": mesh_uri,
            "mesh_sha256": mesh_sha256,
        }
        return cls(
            fixture_part_id=fixture_part_id,
            geometry_revision=geometry_revision,
            slots=ordered,
            design_uri=design_uri,
            design_sha256=design_sha256,
            mesh_uri=mesh_uri,
            mesh_sha256=mesh_sha256,
            fixture_digest=canonical_digest(values),
        )


class ReceiverSlotAssignmentV1(ContractModel):
    """Radio/RX-to-fixture-slot mapping, including its evidential strength."""

    schema_version: Literal[1] = 1
    receiver_id: Annotated[int, Field(ge=0, le=1)]
    physical_receiver_id: Identifier
    slot_id: Identifier
    mapping_status: Literal["verified", "provisional"]
    mapping_evidence: Annotated[str, StringConstraints(min_length=1, max_length=512)]

    @field_validator("mapping_evidence")
    @classmethod
    def _mapping_evidence_is_plain(cls, value: str) -> str:
        if value != value.strip() or any(ord(character) < 0x20 for character in value):
            raise ValueError("mapping evidence must be trimmed plain text")
        return value


def _assignment_key(value: ReceiverSlotAssignmentV1) -> int:
    return value.receiver_id


class RadioReceiverGeometryV1(ContractModel):
    """One radio's exact physical receiver paths installed in one fixture."""

    schema_version: Literal[1] = 1
    radio_id: Identifier
    radio_serial: RadioSerial
    fixture_part_id: Identifier
    fixture_digest: Sha256Digest
    assignments: Annotated[tuple[ReceiverSlotAssignmentV1, ...], Field(min_length=2, max_length=2)]

    @model_validator(mode="after")
    def _complete_canonical_mapping(self) -> Self:
        if tuple(sorted(self.assignments, key=_assignment_key)) != self.assignments:
            raise ValueError("receiver geometry assignments must use canonical RX order")
        if tuple(item.receiver_id for item in self.assignments) != (0, 1):
            raise ValueError("receiver geometry must map RX0 and RX1")
        if len({item.physical_receiver_id for item in self.assignments}) != 2:
            raise ValueError("receiver geometry requires distinct physical receivers")
        if len({item.slot_id for item in self.assignments}) != 2:
            raise ValueError("receiver geometry requires distinct fixture slots")
        return self


def _radio_key(value: RadioReceiverGeometryV1) -> tuple[str, str]:
    return (value.radio_id, value.radio_serial)


def _fixture_key(value: ReceiverFixtureDefinitionV1) -> tuple[str, str]:
    return (value.fixture_part_id, value.fixture_digest)


class StationReceiverGeometryV1(ContractModel):
    """Content-addressed receiver geometry authority for one station interval."""

    schema_version: Literal[1] = 1
    station_id: Identifier
    geometry_revision: Identifier
    valid_from_utc_ns: UtcNs
    valid_until_utc_ns: Annotated[int, Field(gt=0, le=_MAX_UTC_NS)]
    fixtures: Annotated[tuple[ReceiverFixtureDefinitionV1, ...], Field(min_length=1, max_length=16)]
    radios: Annotated[tuple[RadioReceiverGeometryV1, ...], Field(min_length=1, max_length=16)]
    geometry_digest: Sha256Digest

    @model_validator(mode="after")
    def _canonical_complete_authority(self) -> Self:
        if self.valid_until_utc_ns <= self.valid_from_utc_ns:
            raise ValueError("station geometry validity interval must be non-empty")
        if tuple(sorted(self.fixtures, key=_fixture_key)) != self.fixtures:
            raise ValueError("station geometry fixtures must use canonical order")
        if tuple(sorted(self.radios, key=_radio_key)) != self.radios:
            raise ValueError("station geometry radios must use canonical order")
        fixture_ids = {(item.fixture_part_id, item.fixture_digest): item for item in self.fixtures}
        if len(fixture_ids) != len(self.fixtures):
            raise ValueError("station geometry fixture identities must be unique")
        if len({_radio_key(item) for item in self.radios}) != len(self.radios):
            raise ValueError("station geometry radio identities must be unique")
        for radio in self.radios:
            fixture = fixture_ids.get((radio.fixture_part_id, radio.fixture_digest))
            if fixture is None:
                raise ValueError("radio geometry references an unknown fixture")
            if {item.slot_id for item in radio.assignments} != {
                item.slot_id for item in fixture.slots
            }:
                raise ValueError("radio geometry must map every exact fixture slot")
        expected = station_receiver_geometry_digest(self)
        if self.geometry_digest != expected:
            raise ValueError(f"station receiver geometry digest does not match content: {expected}")
        return self

    @classmethod
    def create(
        cls,
        *,
        station_id: str,
        geometry_revision: str,
        valid_from_utc_ns: int,
        valid_until_utc_ns: int,
        fixtures: tuple[ReceiverFixtureDefinitionV1, ...],
        radios: tuple[RadioReceiverGeometryV1, ...],
    ) -> StationReceiverGeometryV1:
        ordered_fixtures = tuple(
            sorted(fixtures, key=_fixture_key)
        )
        ordered_radios = tuple(sorted(radios, key=_radio_key))
        values = {
            "schema_version": 1,
            "station_id": station_id,
            "geometry_revision": geometry_revision,
            "valid_from_utc_ns": valid_from_utc_ns,
            "valid_until_utc_ns": valid_until_utc_ns,
            "fixtures": tuple(item.model_dump(mode="json") for item in ordered_fixtures),
            "radios": tuple(item.model_dump(mode="json") for item in ordered_radios),
        }
        return cls(
            station_id=station_id,
            geometry_revision=geometry_revision,
            valid_from_utc_ns=valid_from_utc_ns,
            valid_until_utc_ns=valid_until_utc_ns,
            fixtures=ordered_fixtures,
            radios=ordered_radios,
            geometry_digest=canonical_digest(values),
        )

    def resolve_path(
        self, path: CapturedHardwarePathV1
    ) -> tuple[RadioReceiverGeometryV1, ReceiverSlotAssignmentV1, ReceiverFixtureSlotV1]:
        if (
            path.capture_start_utc_ns < self.valid_from_utc_ns
            or path.capture_end_utc_ns > self.valid_until_utc_ns
        ):
            raise ValueError("captured path is outside station geometry validity")
        radios = tuple(
            item
            for item in self.radios
            if item.radio_id == path.radio_id and item.radio_serial == path.radio_serial
        )
        if len(radios) != 1:
            raise ValueError("captured radio is absent or ambiguous in station geometry")
        assignments = tuple(
            item
            for item in radios[0].assignments
            if item.receiver_id == path.receiver_id
            and item.physical_receiver_id == path.physical_receiver_id
        )
        if len(assignments) != 1:
            raise ValueError("captured physical path is absent or ambiguous in station geometry")
        fixtures = tuple(
            item
            for item in self.fixtures
            if item.fixture_part_id == radios[0].fixture_part_id
            and item.fixture_digest == radios[0].fixture_digest
        )
        if len(fixtures) != 1:
            raise ValueError("captured radio fixture is absent or ambiguous")
        slots = tuple(item for item in fixtures[0].slots if item.slot_id == assignments[0].slot_id)
        if len(slots) != 1:  # pragma: no cover - station contract already proves this
            raise ValueError("captured receiver fixture slot is absent or ambiguous")
        return radios[0], assignments[0], slots[0]


class CapturedReceiverGeometryPathV1(ContractModel):
    """Capture-time geometry snapshot for one hardware-bound receiver path."""

    schema_version: Literal[1] = 1
    stream_id: Identifier
    radio_id: Identifier
    radio_serial: RadioSerial
    receiver_id: Annotated[int, Field(ge=0, le=1)]
    physical_receiver_id: Identifier
    hardware_epoch_external_id: Identifier
    fixture_part_id: Identifier
    fixture_digest: Sha256Digest
    slot_id: Identifier
    mapping_status: Literal["verified", "provisional"]
    mapping_evidence: Annotated[str, StringConstraints(min_length=1, max_length=512)]
    coordinate_frame: Literal["fixture-local-right-front-up"]
    mount_reference_position_m: CartesianVectorMetersV1
    mount_axis_unit: UnitVectorV1
    rf_phase_center_position_m: CartesianVectorMetersV1 | None = None
    rf_boresight_unit: UnitVectorV1 | None = None


def _captured_geometry_key(value: CapturedReceiverGeometryPathV1) -> tuple[str, str, int]:
    return (value.stream_id, value.radio_id, value.receiver_id)


class CaptureReceiverGeometryBindingV1(ContractModel):
    """Geometry snapshot bound to an immutable capture hardware binding."""

    schema_version: Literal[1] = 1
    hardware_binding: CaptureHardwareBindingV1
    hardware_binding_digest: Sha256Digest
    station_geometry_revision: Identifier
    station_geometry_digest: Sha256Digest
    paths: Annotated[
        tuple[CapturedReceiverGeometryPathV1, ...], Field(min_length=1, max_length=4)
    ]
    binding_digest: Sha256Digest

    @model_validator(mode="after")
    def _matches_hardware_and_digest(self) -> Self:
        if self.hardware_binding_digest != self.hardware_binding.binding_digest:
            raise ValueError("geometry binding differs from its hardware binding")
        if tuple(sorted(self.paths, key=_captured_geometry_key)) != self.paths:
            raise ValueError("captured geometry paths must use canonical order")
        expected_ids = tuple(
            (item.stream_id, item.radio_id, item.receiver_id, item.physical_receiver_id)
            for item in self.hardware_binding.paths
        )
        observed_ids = tuple(
            (item.stream_id, item.radio_id, item.receiver_id, item.physical_receiver_id)
            for item in self.paths
        )
        if observed_ids != expected_ids:
            raise ValueError("geometry paths must exactly match captured hardware paths")
        expected = capture_receiver_geometry_binding_digest(self)
        if self.binding_digest != expected:
            raise ValueError(f"capture receiver geometry digest does not match content: {expected}")
        return self

    @classmethod
    def create(
        cls,
        hardware_binding: CaptureHardwareBindingV1,
        *,
        geometry: StationReceiverGeometryV1,
    ) -> CaptureReceiverGeometryBindingV1:
        if geometry.station_id != hardware_binding.station_id:
            raise ValueError("station geometry and hardware binding station IDs differ")
        paths: list[CapturedReceiverGeometryPathV1] = []
        for path in hardware_binding.paths:
            radio, assignment, slot = geometry.resolve_path(path)
            fixture = next(
                item for item in geometry.fixtures if item.fixture_digest == radio.fixture_digest
            )
            paths.append(
                CapturedReceiverGeometryPathV1(
                    stream_id=path.stream_id,
                    radio_id=path.radio_id,
                    radio_serial=path.radio_serial,
                    receiver_id=path.receiver_id,
                    physical_receiver_id=path.physical_receiver_id,
                    hardware_epoch_external_id=path.hardware_epoch_external_id,
                    fixture_part_id=radio.fixture_part_id,
                    fixture_digest=radio.fixture_digest,
                    slot_id=assignment.slot_id,
                    mapping_status=assignment.mapping_status,
                    mapping_evidence=assignment.mapping_evidence,
                    coordinate_frame=fixture.coordinate_frame,
                    mount_reference_position_m=slot.mount_reference_position_m,
                    mount_axis_unit=slot.mount_axis_unit,
                    rf_phase_center_position_m=slot.rf_phase_center_position_m,
                    rf_boresight_unit=slot.rf_boresight_unit,
                )
            )
        ordered = tuple(sorted(paths, key=_captured_geometry_key))
        values = {
            "schema_version": 1,
            "hardware_binding": hardware_binding.model_dump(mode="json"),
            "hardware_binding_digest": hardware_binding.binding_digest,
            "station_geometry_revision": geometry.geometry_revision,
            "station_geometry_digest": geometry.geometry_digest,
            "paths": tuple(item.model_dump(mode="json") for item in ordered),
        }
        return cls(
            hardware_binding=hardware_binding,
            hardware_binding_digest=hardware_binding.binding_digest,
            station_geometry_revision=geometry.geometry_revision,
            station_geometry_digest=geometry.geometry_digest,
            paths=ordered,
            binding_digest=canonical_digest(values),
        )


class AdaptiveReceiverGeometryBindingV1(ContractModel):
    """Self-contained geometry snapshot for one dual-receiver adaptive recording."""

    schema_version: Literal[1] = 1
    station_id: Identifier
    station_geometry_revision: Identifier
    station_geometry_digest: Sha256Digest
    valid_from_utc_ns: UtcNs
    valid_until_utc_ns: Annotated[int, Field(gt=0, le=_MAX_UTC_NS)]
    radio: RadioReceiverGeometryV1
    fixture: ReceiverFixtureDefinitionV1
    binding_digest: Sha256Digest

    @model_validator(mode="after")
    def _closed_snapshot(self) -> Self:
        if self.valid_until_utc_ns <= self.valid_from_utc_ns:
            raise ValueError("adaptive geometry validity interval must be non-empty")
        if (
            self.radio.fixture_part_id != self.fixture.fixture_part_id
            or self.radio.fixture_digest != self.fixture.fixture_digest
        ):
            raise ValueError("adaptive radio geometry differs from its fixture")
        if {item.slot_id for item in self.radio.assignments} != {
            item.slot_id for item in self.fixture.slots
        }:
            raise ValueError("adaptive geometry must bind both fixture slots")
        expected = adaptive_receiver_geometry_binding_digest(self)
        if self.binding_digest != expected:
            raise ValueError(
                f"adaptive receiver geometry digest does not match content: {expected}"
            )
        return self

    @classmethod
    def create(
        cls,
        geometry: StationReceiverGeometryV1,
        *,
        radio_id: str,
        radio_serial: str,
    ) -> AdaptiveReceiverGeometryBindingV1:
        radios = tuple(
            item
            for item in geometry.radios
            if item.radio_id == radio_id and item.radio_serial == radio_serial
        )
        if len(radios) != 1:
            raise ValueError("adaptive radio is absent or ambiguous in station geometry")
        radio = radios[0]
        fixture = next(
            item
            for item in geometry.fixtures
            if item.fixture_part_id == radio.fixture_part_id
            and item.fixture_digest == radio.fixture_digest
        )
        values = {
            "schema_version": 1,
            "station_id": geometry.station_id,
            "station_geometry_revision": geometry.geometry_revision,
            "station_geometry_digest": geometry.geometry_digest,
            "valid_from_utc_ns": geometry.valid_from_utc_ns,
            "valid_until_utc_ns": geometry.valid_until_utc_ns,
            "radio": radio.model_dump(mode="json"),
            "fixture": fixture.model_dump(mode="json"),
        }
        return cls(
            **values,
            binding_digest=canonical_digest(values),
        )


def receiver_fixture_digest(value: ReceiverFixtureDefinitionV1) -> str:
    return canonical_digest(value.model_dump(mode="json", exclude={"fixture_digest"}))


def station_receiver_geometry_digest(value: StationReceiverGeometryV1) -> str:
    return canonical_digest(value.model_dump(mode="json", exclude={"geometry_digest"}))


def capture_receiver_geometry_binding_digest(value: CaptureReceiverGeometryBindingV1) -> str:
    return canonical_digest(value.model_dump(mode="json", exclude={"binding_digest"}))


def adaptive_receiver_geometry_binding_digest(value: AdaptiveReceiverGeometryBindingV1) -> str:
    return canonical_digest(value.model_dump(mode="json", exclude={"binding_digest"}))
