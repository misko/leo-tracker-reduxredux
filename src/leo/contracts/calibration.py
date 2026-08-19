"""Immutable receiver-frequency calibration contracts.

The calibration value is an analysis input, not mutable station state.  A
calibration names one physical receive path and carries enough provenance to
decide whether it was valid when a recording was made.
"""

from __future__ import annotations

import math
from typing import Annotated, Literal, Self

from pydantic import Field, StringConstraints, field_validator, model_validator

from leo.contracts.base import ContractModel
from leo.contracts.digests import Sha256Digest, canonical_digest
from leo.contracts.recording import Identifier


class CalibrationEvidenceV1(ContractModel):
    schema_version: Literal[1] = 1
    kind: Annotated[str, StringConstraints(min_length=1, max_length=96)]
    uri: Annotated[str, StringConstraints(min_length=1, max_length=2048)]
    digest: Sha256Digest
    source_revision: Annotated[
        str | None,
        StringConstraints(min_length=1, max_length=128),
    ] = None


class ReceiverPathIdentityV1(ContractModel):
    """Physical receive-path identity at one capture instant."""

    schema_version: Literal[1] = 1
    radio_id: Identifier
    radio_serial: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    receiver_id: Annotated[int, Field(ge=0, le=1)]
    physical_receiver_id: Identifier
    capture_utc_ns: Annotated[int, Field(ge=0)]


class ReceiverFrequencyCalibrationV1(ContractModel):
    """Content-addressed absolute baseband center for one physical path.

    Validity is the half-open interval ``[valid_from_utc_ns,
    valid_until_utc_ns)``; a null upper bound means the interval is open-ended.
    """

    schema_version: Literal[1] = 1
    calibration_id: Identifier
    calibration_digest: Sha256Digest
    radio_id: Identifier
    radio_serial: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    receiver_id: Annotated[int, Field(ge=0, le=1)]
    physical_receiver_id: Identifier
    center_hz: float
    uncertainty_lower_hz: float
    uncertainty_upper_hz: float
    valid_from_utc_ns: Annotated[int, Field(ge=0)]
    valid_until_utc_ns: Annotated[int | None, Field(ge=0)] = None
    method: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    created_utc_ns: Annotated[int, Field(ge=0)]
    evidence: tuple[CalibrationEvidenceV1, ...]

    @field_validator("center_hz", "uncertainty_lower_hz", "uncertainty_upper_hz")
    @classmethod
    def _frequency_values_are_finite(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("calibration frequency values must be finite")
        return value

    @model_validator(mode="after")
    def _validate_identity_interval_and_digest(self) -> Self:
        if self.uncertainty_lower_hz > self.center_hz:
            raise ValueError("calibration lower uncertainty bound exceeds center")
        if self.uncertainty_upper_hz < self.center_hz:
            raise ValueError("calibration upper uncertainty bound precedes center")
        if (
            self.valid_until_utc_ns is not None
            and self.valid_until_utc_ns <= self.valid_from_utc_ns
        ):
            raise ValueError("calibration validity interval must be non-empty")
        if not self.evidence:
            raise ValueError("calibration requires immutable evidence provenance")
        if len({(item.kind, item.uri, item.digest) for item in self.evidence}) != len(
            self.evidence
        ):
            raise ValueError("calibration evidence entries must be unique")
        expected = receiver_frequency_calibration_digest(self)
        if self.calibration_digest != expected:
            raise ValueError(f"calibration digest does not match content: {expected}")
        return self

    @classmethod
    def create(
        cls,
        *,
        calibration_id: str,
        radio_id: str,
        radio_serial: str,
        receiver_id: int,
        physical_receiver_id: str,
        center_hz: float,
        uncertainty_lower_hz: float,
        uncertainty_upper_hz: float,
        valid_from_utc_ns: int,
        valid_until_utc_ns: int | None,
        method: str,
        created_utc_ns: int,
        evidence: tuple[CalibrationEvidenceV1, ...],
    ) -> ReceiverFrequencyCalibrationV1:
        values = {
            "schema_version": 1,
            "calibration_id": calibration_id,
            "radio_id": radio_id,
            "radio_serial": radio_serial,
            "receiver_id": receiver_id,
            "physical_receiver_id": physical_receiver_id,
            "center_hz": float(center_hz),
            "uncertainty_lower_hz": float(uncertainty_lower_hz),
            "uncertainty_upper_hz": float(uncertainty_upper_hz),
            "valid_from_utc_ns": valid_from_utc_ns,
            "valid_until_utc_ns": valid_until_utc_ns,
            "method": method,
            "created_utc_ns": created_utc_ns,
            "evidence": tuple(item.model_dump(mode="json") for item in evidence),
        }
        digest = canonical_digest(values)
        return cls(
            calibration_digest=digest,
            schema_version=1,
            calibration_id=calibration_id,
            radio_id=radio_id,
            radio_serial=radio_serial,
            receiver_id=receiver_id,
            physical_receiver_id=physical_receiver_id,
            center_hz=center_hz,
            uncertainty_lower_hz=uncertainty_lower_hz,
            uncertainty_upper_hz=uncertainty_upper_hz,
            valid_from_utc_ns=valid_from_utc_ns,
            valid_until_utc_ns=valid_until_utc_ns,
            method=method,
            created_utc_ns=created_utc_ns,
            evidence=evidence,
        )

    def matches(self, identity: ReceiverPathIdentityV1) -> bool:
        if (
            self.radio_id != identity.radio_id
            or self.radio_serial != identity.radio_serial
            or self.receiver_id != identity.receiver_id
            or self.physical_receiver_id != identity.physical_receiver_id
        ):
            return False
        return self.valid_from_utc_ns <= identity.capture_utc_ns and (
            self.valid_until_utc_ns is None or identity.capture_utc_ns < self.valid_until_utc_ns
        )


class ReceiverFrequencyCalibrationSetV1(ContractModel):
    schema_version: Literal[1] = 1
    calibration_set_id: Identifier
    calibration_set_digest: Sha256Digest
    calibrations: tuple[ReceiverFrequencyCalibrationV1, ...]

    @model_validator(mode="after")
    def _validate_members_and_digest(self) -> Self:
        if not self.calibrations:
            raise ValueError("calibration set must not be empty")
        identities = tuple(
            (
                item.radio_id,
                item.radio_serial,
                item.receiver_id,
                item.physical_receiver_id,
                item.valid_from_utc_ns,
                item.valid_until_utc_ns,
            )
            for item in self.calibrations
        )
        canonical = tuple(
            sorted(
                identities,
                key=lambda item: (*item[:-1], item[-1] if item[-1] is not None else 2**64),
            )
        )
        if canonical != identities or len(set(identities)) != len(identities):
            raise ValueError("calibrations must have unique canonical identity/validity order")
        previous_by_path: dict[tuple[str, str, int, str], ReceiverFrequencyCalibrationV1] = {}
        for item in self.calibrations:
            path = (item.radio_id, item.radio_serial, item.receiver_id, item.physical_receiver_id)
            previous = previous_by_path.get(path)
            if previous is not None and (
                previous.valid_until_utc_ns is None
                or item.valid_from_utc_ns < previous.valid_until_utc_ns
            ):
                raise ValueError("calibration validity intervals overlap for one physical path")
            previous_by_path[path] = item
        expected = receiver_frequency_calibration_set_digest(self)
        if self.calibration_set_digest != expected:
            raise ValueError(f"calibration-set digest does not match content: {expected}")
        return self

    @classmethod
    def create(
        cls,
        *,
        calibration_set_id: str,
        calibrations: tuple[ReceiverFrequencyCalibrationV1, ...],
    ) -> ReceiverFrequencyCalibrationSetV1:
        ordered = tuple(
            sorted(
                calibrations,
                key=lambda item: (
                    item.radio_id,
                    item.radio_serial,
                    item.receiver_id,
                    item.physical_receiver_id,
                    item.valid_from_utc_ns,
                    item.valid_until_utc_ns if item.valid_until_utc_ns is not None else 2**64,
                ),
            )
        )
        values = {
            "schema_version": 1,
            "calibration_set_id": calibration_set_id,
            "calibrations": ordered,
        }
        return cls(
            calibration_set_digest=canonical_digest(
                {
                    **values,
                    "calibrations": tuple(item.model_dump(mode="json") for item in ordered),
                }
            ),
            schema_version=1,
            calibration_set_id=calibration_set_id,
            calibrations=ordered,
        )

    def resolve(self, identity: ReceiverPathIdentityV1) -> ReceiverFrequencyCalibrationV1 | None:
        matches = tuple(item for item in self.calibrations if item.matches(identity))
        if len(matches) > 1:
            raise ValueError("calibration set contains overlapping valid calibrations")
        return matches[0] if matches else None


def receiver_frequency_calibration_digest(value: ReceiverFrequencyCalibrationV1) -> str:
    return canonical_digest(_json_mapping(value))


def receiver_frequency_calibration_set_digest(value: ReceiverFrequencyCalibrationSetV1) -> str:
    return canonical_digest(_json_mapping(value))


def _json_mapping(value: ContractModel) -> dict[str, object]:
    return value.model_dump(mode="json", exclude={"calibration_digest", "calibration_set_digest"})
