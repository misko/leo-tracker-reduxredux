"""Immutable station receiver-lineage authority contracts.

These documents establish hardware identity only.  They do not contain or
imply receiver-frequency calibration.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Annotated, Literal, Self

from pydantic import Field, StringConstraints, field_validator, model_validator

from leo.contracts.base import ContractModel
from leo.contracts.digests import Sha256Digest, canonical_digest
from leo.contracts.recording import Identifier
from leo.contracts.states import RadioTransport

_MAX_UTC_NS = 9_223_372_036_854_775_807
UtcNs = Annotated[int, Field(ge=0, le=_MAX_UTC_NS)]
RadioSerial = Annotated[str, StringConstraints(min_length=1, max_length=128)]
EvidenceUri = Annotated[str, StringConstraints(min_length=1, max_length=2048)]
Endpoint = Annotated[str, StringConstraints(min_length=1, max_length=512)]


def _plain_text(value: str) -> str:
    if value != value.strip() or any(ord(character) < 0x20 for character in value):
        raise ValueError("authority text must be trimmed and contain no control characters")
    return value


class RadioEndpointEvidenceV1(ContractModel):
    """Exact configured endpoint plus immutable evidence for that assertion."""

    schema_version: Literal[1] = 1
    transport: RadioTransport
    endpoint: Endpoint
    evidence_uri: EvidenceUri
    evidence_digest: Sha256Digest

    _endpoint_is_plain = field_validator("endpoint")(_plain_text)
    _evidence_uri_is_plain = field_validator("evidence_uri")(_plain_text)


class StationReceiverAssignmentV1(ContractModel):
    """One exact, half-open physical-path assignment during a hardware epoch."""

    schema_version: Literal[1] = 1
    receiver_id: Annotated[int, Field(ge=0, le=1)]
    physical_receiver_id: Identifier
    hardware_epoch_external_id: Identifier
    valid_from_utc_ns: UtcNs
    valid_until_utc_ns: Annotated[int, Field(gt=0, le=_MAX_UTC_NS)]

    @model_validator(mode="after")
    def _interval_is_nonempty(self) -> Self:
        if self.valid_until_utc_ns <= self.valid_from_utc_ns:
            raise ValueError("receiver assignment validity interval must be non-empty")
        return self


def _assignment_key(
    value: StationReceiverAssignmentV1,
) -> tuple[int, int, int, str, str]:
    return (
        value.receiver_id,
        value.valid_from_utc_ns,
        value.valid_until_utc_ns,
        value.physical_receiver_id,
        value.hardware_epoch_external_id,
    )


class StationRadioTopologyV1(ContractModel):
    """One complete two-receiver radio inventory in station topology."""

    schema_version: Literal[1] = 1
    radio_id: Identifier
    radio_serial: RadioSerial
    endpoint_evidence: RadioEndpointEvidenceV1
    receiver_assignments: Annotated[
        tuple[StationReceiverAssignmentV1, ...],
        Field(min_length=1, max_length=32),
    ]

    @model_validator(mode="after")
    def _inventory_is_complete_unique_and_canonical(self) -> Self:
        assignments = self.receiver_assignments
        if tuple(sorted(assignments, key=_assignment_key)) != assignments:
            raise ValueError("receiver assignments must use canonical receiver/time order")
        identities = tuple(_assignment_key(item) for item in assignments)
        if len(set(identities)) != len(identities):
            raise ValueError("receiver assignments must be unique")
        by_receiver: dict[int, list[StationReceiverAssignmentV1]] = defaultdict(list)
        for item in assignments:
            by_receiver[item.receiver_id].append(item)
        if set(by_receiver) != {0, 1}:
            raise ValueError("station radio inventory cannot omit RX0 or RX1")
        for receiver_id, path_assignments in by_receiver.items():
            physical_ids = {item.physical_receiver_id for item in path_assignments}
            if len(physical_ids) != 1:
                raise ValueError(
                    f"RX{receiver_id} physical receiver identity cannot change in one topology"
                )
            for previous, current in zip(path_assignments, path_assignments[1:], strict=False):
                if current.valid_from_utc_ns < previous.valid_until_utc_ns:
                    raise ValueError(
                        f"receiver assignment validity intervals overlap for RX{receiver_id}"
                    )
        if (
            len(
                {
                    path_assignments[0].physical_receiver_id
                    for path_assignments in by_receiver.values()
                }
            )
            != 2
        ):
            raise ValueError("RX0 and RX1 require distinct physical receiver identities")
        return self

    @classmethod
    def create(
        cls,
        *,
        radio_id: str,
        radio_serial: str,
        endpoint_evidence: RadioEndpointEvidenceV1,
        receiver_assignments: tuple[StationReceiverAssignmentV1, ...],
    ) -> StationRadioTopologyV1:
        return cls(
            radio_id=radio_id,
            radio_serial=radio_serial,
            endpoint_evidence=endpoint_evidence,
            receiver_assignments=tuple(sorted(receiver_assignments, key=_assignment_key)),
        )


def _radio_key(value: StationRadioTopologyV1) -> tuple[str, str, str, str, str, str]:
    endpoint = value.endpoint_evidence
    return (
        value.radio_id,
        value.radio_serial,
        endpoint.transport.value,
        endpoint.endpoint,
        endpoint.evidence_uri,
        endpoint.evidence_digest,
    )


class StationReceiverTopologyV1(ContractModel):
    """Content-addressed station path authority for one exact UTC interval.

    Every listed radio has complete RX0/RX1 coverage.  Each receiver's ordered
    assignments must exactly partition the topology interval, without a gap or
    overlap.  A new hardware epoch therefore requires an explicit bounded
    assignment rather than a mutable station-state lookup.
    """

    schema_version: Literal[1] = 1
    station_id: Identifier
    topology_revision: Identifier
    valid_from_utc_ns: UtcNs
    valid_until_utc_ns: Annotated[int, Field(gt=0, le=_MAX_UTC_NS)]
    radios: Annotated[tuple[StationRadioTopologyV1, ...], Field(min_length=1, max_length=16)]
    topology_digest: Sha256Digest

    @model_validator(mode="after")
    def _validate_inventory_intervals_and_digest(self) -> Self:
        if self.valid_until_utc_ns <= self.valid_from_utc_ns:
            raise ValueError("station topology validity interval must be non-empty")
        if tuple(sorted(self.radios, key=_radio_key)) != self.radios:
            raise ValueError("station radios must use canonical identity order")
        radio_ids = tuple(item.radio_id for item in self.radios)
        serials = tuple(item.radio_serial for item in self.radios)
        endpoints = tuple(
            (item.endpoint_evidence.transport, item.endpoint_evidence.endpoint)
            for item in self.radios
        )
        if len(set(radio_ids)) != len(radio_ids):
            raise ValueError("station radio IDs must be unique")
        if len(set(serials)) != len(serials):
            raise ValueError("station radio serials must be unique")
        if len(set(endpoints)) != len(endpoints):
            raise ValueError("station transport/endpoint identities must be unique")

        physical_owners: dict[str, tuple[str, int]] = {}
        for radio in self.radios:
            by_receiver: dict[int, list[StationReceiverAssignmentV1]] = defaultdict(list)
            for assignment in radio.receiver_assignments:
                by_receiver[assignment.receiver_id].append(assignment)
                owner = (radio.radio_id, assignment.receiver_id)
                previous_owner = physical_owners.setdefault(
                    assignment.physical_receiver_id, owner
                )
                if previous_owner != owner:
                    raise ValueError(
                        "physical receiver identity cannot belong to multiple radio paths"
                    )
            for receiver_id, assignments in by_receiver.items():
                if (
                    assignments[0].valid_from_utc_ns != self.valid_from_utc_ns
                    or assignments[-1].valid_until_utc_ns != self.valid_until_utc_ns
                ):
                    raise ValueError(
                        f"RX{receiver_id} assignments must cover the full topology interval"
                    )
                for previous, current in zip(assignments, assignments[1:], strict=False):
                    if current.valid_from_utc_ns != previous.valid_until_utc_ns:
                        raise ValueError(
                            f"RX{receiver_id} assignment intervals must be exactly contiguous"
                        )

        expected = station_receiver_topology_digest(self)
        if self.topology_digest != expected:
            raise ValueError(f"station topology digest does not match content: {expected}")
        return self

    @classmethod
    def create(
        cls,
        *,
        station_id: str,
        topology_revision: str,
        valid_from_utc_ns: int,
        valid_until_utc_ns: int,
        radios: tuple[StationRadioTopologyV1, ...],
    ) -> StationReceiverTopologyV1:
        ordered = tuple(sorted(radios, key=_radio_key))
        digest_values = {
            "schema_version": 1,
            "station_id": station_id,
            "topology_revision": topology_revision,
            "valid_from_utc_ns": valid_from_utc_ns,
            "valid_until_utc_ns": valid_until_utc_ns,
            "radios": tuple(item.model_dump(mode="json") for item in ordered),
        }
        return cls(
            station_id=station_id,
            topology_revision=topology_revision,
            valid_from_utc_ns=valid_from_utc_ns,
            valid_until_utc_ns=valid_until_utc_ns,
            radios=ordered,
            topology_digest=canonical_digest(digest_values),
        )

    def resolve_assignment(
        self,
        *,
        radio_id: str,
        radio_serial: str,
        receiver_id: int,
        capture_start_utc_ns: int,
        capture_end_utc_ns: int,
    ) -> tuple[StationRadioTopologyV1, StationReceiverAssignmentV1]:
        """Resolve one assignment that covers the complete capture interval."""

        if capture_end_utc_ns <= capture_start_utc_ns:
            raise ValueError("capture interval must be non-empty")
        if (
            capture_start_utc_ns < self.valid_from_utc_ns
            or capture_end_utc_ns > self.valid_until_utc_ns
        ):
            raise ValueError("capture interval is outside station topology validity")
        radios = tuple(item for item in self.radios if item.radio_id == radio_id)
        if len(radios) != 1 or radios[0].radio_serial != radio_serial:
            raise ValueError("capture radio ID/serial is not in station topology")
        matches = tuple(
            item
            for item in radios[0].receiver_assignments
            if item.receiver_id == receiver_id
            and item.valid_from_utc_ns <= capture_start_utc_ns
            and capture_end_utc_ns <= item.valid_until_utc_ns
        )
        if len(matches) != 1:
            raise ValueError("capture crosses or lacks one exact hardware-epoch assignment")
        return radios[0], matches[0]


class CapturePathSelectorV1(ContractModel):
    """Manifest facts used to resolve one recorded receiver path."""

    schema_version: Literal[1] = 1
    stream_id: Identifier
    radio_id: Identifier
    radio_serial: RadioSerial
    receiver_id: Annotated[int, Field(ge=0, le=1)]


class CapturedHardwarePathV1(ContractModel):
    """Resolved immutable hardware identity for one recorded receiver path."""

    schema_version: Literal[1] = 1
    stream_id: Identifier
    radio_id: Identifier
    radio_serial: RadioSerial
    receiver_id: Annotated[int, Field(ge=0, le=1)]
    physical_receiver_id: Identifier
    hardware_epoch_external_id: Identifier
    radio_transport: RadioTransport
    radio_endpoint: Endpoint
    endpoint_evidence_uri: EvidenceUri
    endpoint_evidence_digest: Sha256Digest

    _radio_endpoint_is_plain = field_validator("radio_endpoint")(_plain_text)
    _endpoint_evidence_uri_is_plain = field_validator("endpoint_evidence_uri")(_plain_text)


def _captured_path_key(value: CapturedHardwarePathV1) -> tuple[str, str, int]:
    return (value.stream_id, value.radio_id, value.receiver_id)


class CaptureHardwareBindingV1(ContractModel):
    """Capture-time snapshot bound to one manifest and station topology."""

    schema_version: Literal[1] = 1
    session_id: Identifier
    manifest_digest: Sha256Digest
    capture_start_utc_ns: UtcNs
    capture_end_utc_ns: Annotated[int, Field(gt=0, le=_MAX_UTC_NS)]
    station_id: Identifier
    topology_revision: Identifier
    topology_digest: Sha256Digest
    paths: Annotated[tuple[CapturedHardwarePathV1, ...], Field(min_length=1, max_length=32)]
    binding_digest: Sha256Digest

    @model_validator(mode="after")
    def _validate_inventory_and_digest(self) -> Self:
        if self.capture_end_utc_ns <= self.capture_start_utc_ns:
            raise ValueError("capture hardware binding interval must be non-empty")
        if tuple(sorted(self.paths, key=_captured_path_key)) != self.paths:
            raise ValueError("capture hardware paths must use canonical stream/radio/RX order")
        path_ids = tuple((item.stream_id, item.receiver_id) for item in self.paths)
        hardware_ids = tuple(
            (item.radio_id, item.receiver_id, item.physical_receiver_id) for item in self.paths
        )
        if len(set(path_ids)) != len(path_ids) or len(set(hardware_ids)) != len(hardware_ids):
            raise ValueError("capture hardware paths must be unique")
        stream_radios: dict[str, tuple[str, str, RadioTransport, str, str, str]] = {}
        radio_streams: dict[str, str] = {}
        for item in self.paths:
            identity = (
                item.radio_id,
                item.radio_serial,
                item.radio_transport,
                item.radio_endpoint,
                item.endpoint_evidence_uri,
                item.endpoint_evidence_digest,
            )
            previous = stream_radios.setdefault(item.stream_id, identity)
            if previous != identity:
                raise ValueError("one capture stream cannot contain multiple radio identities")
            previous_stream = radio_streams.setdefault(item.radio_id, item.stream_id)
            if previous_stream != item.stream_id:
                raise ValueError("one capture radio cannot appear under multiple stream IDs")
        expected = capture_hardware_binding_digest(self)
        if self.binding_digest != expected:
            raise ValueError(f"capture hardware binding digest does not match content: {expected}")
        return self

    @classmethod
    def create(
        cls,
        *,
        session_id: str,
        manifest_digest: str,
        capture_start_utc_ns: int,
        capture_end_utc_ns: int,
        topology: StationReceiverTopologyV1,
        selectors: tuple[CapturePathSelectorV1, ...],
    ) -> CaptureHardwareBindingV1:
        if not selectors:
            raise ValueError("capture hardware binding requires at least one selected path")
        paths: list[CapturedHardwarePathV1] = []
        for selector in selectors:
            radio, assignment = topology.resolve_assignment(
                radio_id=selector.radio_id,
                radio_serial=selector.radio_serial,
                receiver_id=selector.receiver_id,
                capture_start_utc_ns=capture_start_utc_ns,
                capture_end_utc_ns=capture_end_utc_ns,
            )
            evidence = radio.endpoint_evidence
            paths.append(
                CapturedHardwarePathV1(
                    stream_id=selector.stream_id,
                    radio_id=selector.radio_id,
                    radio_serial=selector.radio_serial,
                    receiver_id=selector.receiver_id,
                    physical_receiver_id=assignment.physical_receiver_id,
                    hardware_epoch_external_id=assignment.hardware_epoch_external_id,
                    radio_transport=evidence.transport,
                    radio_endpoint=evidence.endpoint,
                    endpoint_evidence_uri=evidence.evidence_uri,
                    endpoint_evidence_digest=evidence.evidence_digest,
                )
            )
        ordered = tuple(sorted(paths, key=_captured_path_key))
        digest_values = {
            "schema_version": 1,
            "session_id": session_id,
            "manifest_digest": manifest_digest,
            "capture_start_utc_ns": capture_start_utc_ns,
            "capture_end_utc_ns": capture_end_utc_ns,
            "station_id": topology.station_id,
            "topology_revision": topology.topology_revision,
            "topology_digest": topology.topology_digest,
            "paths": tuple(item.model_dump(mode="json") for item in ordered),
        }
        return cls(
            session_id=session_id,
            manifest_digest=manifest_digest,
            capture_start_utc_ns=capture_start_utc_ns,
            capture_end_utc_ns=capture_end_utc_ns,
            station_id=topology.station_id,
            topology_revision=topology.topology_revision,
            topology_digest=topology.topology_digest,
            paths=ordered,
            binding_digest=canonical_digest(digest_values),
        )

    def assert_matches_topology(self, topology: StationReceiverTopologyV1) -> None:
        """Fail closed if this snapshot cannot be re-derived from the authority."""

        if (
            topology.station_id != self.station_id
            or topology.topology_revision != self.topology_revision
            or topology.topology_digest != self.topology_digest
        ):
            raise ValueError("capture binding topology identity has been retargeted")
        for path in self.paths:
            radio, assignment = topology.resolve_assignment(
                radio_id=path.radio_id,
                radio_serial=path.radio_serial,
                receiver_id=path.receiver_id,
                capture_start_utc_ns=self.capture_start_utc_ns,
                capture_end_utc_ns=self.capture_end_utc_ns,
            )
            evidence = radio.endpoint_evidence
            expected = (
                assignment.physical_receiver_id,
                assignment.hardware_epoch_external_id,
                evidence.transport,
                evidence.endpoint,
                evidence.evidence_uri,
                evidence.evidence_digest,
            )
            observed = (
                path.physical_receiver_id,
                path.hardware_epoch_external_id,
                path.radio_transport,
                path.radio_endpoint,
                path.endpoint_evidence_uri,
                path.endpoint_evidence_digest,
            )
            if observed != expected:
                raise ValueError("capture hardware path differs from station topology")


class FixtureStreamPathInventoryV1(ContractModel):
    """Observable manifest identity for one protected TEST stream."""

    schema_version: Literal[1] = 1
    stream_id: Identifier
    radio_id: Identifier
    radio_serial: RadioSerial
    receiver_ids: Annotated[
        tuple[Annotated[int, Field(ge=0, le=1)], ...],
        Field(min_length=1, max_length=2),
    ]

    @field_validator("receiver_ids")
    @classmethod
    def _receiver_ids_are_canonical(cls, value: tuple[int, ...]) -> tuple[int, ...]:
        if tuple(sorted(set(value))) != value:
            raise ValueError("fixture receiver IDs must be unique and canonical")
        return value


def _fixture_stream_key(value: FixtureStreamPathInventoryV1) -> tuple[str, str, str]:
    return (value.stream_id, value.radio_id, value.radio_serial)


class FixturePathAuthorityV1(ContractModel):
    """Evidence-only identity for a protected TEST fixture.

    This contract deliberately has no physical-path, hardware-epoch, or
    calibration fields.  Literal false gates make it impossible to promote the
    fixture to current analysis or physical association by data mutation.
    """

    schema_version: Literal[1] = 1
    authority_kind: Literal["protected-test-evidence-only"] = (
        "protected-test-evidence-only"
    )
    source_type: Literal["test"] = "test"
    session_id: Identifier
    manifest_digest: Sha256Digest
    streams: Annotated[
        tuple[FixtureStreamPathInventoryV1, ...],
        Field(min_length=1, max_length=16),
    ]
    lineage_status: Literal["unresolved"] = "unresolved"
    evidence_only: Literal[True] = True
    current_analysis_eligible: Literal[False] = False
    physical_association_permitted: Literal[False] = False
    calibration_association_permitted: Literal[False] = False
    promotion_permitted: Literal[False] = False
    authority_digest: Sha256Digest

    @model_validator(mode="after")
    def _validate_inventory_and_digest(self) -> Self:
        if tuple(sorted(self.streams, key=_fixture_stream_key)) != self.streams:
            raise ValueError("fixture streams must use canonical stream/radio order")
        stream_ids = tuple(item.stream_id for item in self.streams)
        radio_ids = tuple(item.radio_id for item in self.streams)
        serials = tuple(item.radio_serial for item in self.streams)
        if len(set(stream_ids)) != len(stream_ids):
            raise ValueError("fixture stream IDs must be unique")
        if len(set(radio_ids)) != len(radio_ids):
            raise ValueError("fixture radio IDs must be unique")
        if len(set(serials)) != len(serials):
            raise ValueError("fixture radio serials must be unique")
        expected = fixture_path_authority_digest(self)
        if self.authority_digest != expected:
            raise ValueError(f"fixture authority digest does not match content: {expected}")
        return self

    @classmethod
    def create(
        cls,
        *,
        session_id: str,
        manifest_digest: str,
        streams: tuple[FixtureStreamPathInventoryV1, ...],
    ) -> FixturePathAuthorityV1:
        ordered = tuple(sorted(streams, key=_fixture_stream_key))
        digest_values = {
            "schema_version": 1,
            "authority_kind": "protected-test-evidence-only",
            "source_type": "test",
            "session_id": session_id,
            "manifest_digest": manifest_digest,
            "streams": tuple(item.model_dump(mode="json") for item in ordered),
            "lineage_status": "unresolved",
            "evidence_only": True,
            "current_analysis_eligible": False,
            "physical_association_permitted": False,
            "calibration_association_permitted": False,
            "promotion_permitted": False,
        }
        return cls(
            session_id=session_id,
            manifest_digest=manifest_digest,
            streams=ordered,
            authority_digest=canonical_digest(digest_values),
        )


def station_receiver_topology_digest(value: StationReceiverTopologyV1) -> str:
    return canonical_digest(value.model_dump(mode="json", exclude={"topology_digest"}))


def capture_hardware_binding_digest(value: CaptureHardwareBindingV1) -> str:
    return canonical_digest(value.model_dump(mode="json", exclude={"binding_digest"}))


def fixture_path_authority_digest(value: FixturePathAuthorityV1) -> str:
    return canonical_digest(value.model_dump(mode="json", exclude={"authority_digest"}))
