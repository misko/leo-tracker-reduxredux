"""Narrow contract adapter for the authoritative PostgreSQL calibration catalog."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from leo.application.frequency_calibration import DurableCalibrationPublicationRefV1
from leo.catalog import (
    CatalogRepository,
    FrequencyCalibrationRegistration,
    FrequencyCalibrationSetRegistration,
    ReceiverPathRegistration,
)
from leo.contracts.calibration import (
    ReceiverFrequencyCalibrationSetV1,
    ReceiverFrequencyCalibrationV1,
    ReceiverPathIdentityV1,
)


@dataclass(frozen=True, slots=True)
class ResolvedFrequencyCalibration:
    calibration: ReceiverFrequencyCalibrationV1
    calibration_set: ReceiverFrequencyCalibrationSetV1


@dataclass(frozen=True, slots=True)
class AuthoritativeCalibrationPublication:
    publication: DurableCalibrationPublicationRefV1
    calibration_set: ReceiverFrequencyCalibrationSetV1


class AuthoritativeCalibrationResolverPort(Protocol):
    def resolve(
        self,
        ref: DurableCalibrationPublicationRefV1,
    ) -> ReceiverFrequencyCalibrationSetV1: ...


class CalibrationCatalogPort(Protocol):
    def publish(
        self,
        publication: DurableCalibrationPublicationRefV1,
    ) -> AuthoritativeCalibrationPublication: ...

    def lookup(self, promotion_id: str) -> AuthoritativeCalibrationPublication: ...

    def resolve(self, identity: ReceiverPathIdentityV1) -> ResolvedFrequencyCalibration: ...


class PostgresCalibrationCatalogAdapter:
    def __init__(
        self,
        repository: CatalogRepository,
        authoritative: AuthoritativeCalibrationResolverPort,
    ) -> None:
        self._repository = repository
        self._authoritative = authoritative

    def register_receiver_path(
        self,
        identity: ReceiverPathIdentityV1,
        *,
        radio_uri: str,
        transport: str,
        hardware_epoch_started_utc_ns: int,
    ) -> None:
        self._repository.register_receiver_path(
            ReceiverPathRegistration(
                radio_id=identity.radio_id,
                radio_serial=identity.radio_serial,
                radio_uri=radio_uri,
                transport=transport,
                receiver_id=identity.receiver_id,
                physical_receiver_id=identity.physical_receiver_id,
                hardware_epoch_id=identity.hardware_epoch_id,
                hardware_epoch_started_utc_ns=hardware_epoch_started_utc_ns,
            )
        )

    def publish(
        self,
        publication: DurableCalibrationPublicationRefV1,
    ) -> AuthoritativeCalibrationPublication:
        value = self._authoritative.resolve(publication)
        registration = FrequencyCalibrationSetRegistration(
            set_id=value.calibration_set_id,
            set_digest=value.calibration_set_digest,
            promotion_id=publication.promotion_id,
            sealed_utc_ns=publication.sealed_utc_ns,
            evidence_uri=publication.bundle_uri,
            evidence_digest=publication.manifest_digest,
            calibrations=tuple(
                _calibration_registration(
                    item,
                    publication.bundle_uri,
                    publication.manifest_digest,
                )
                for item in value.calibrations
            ),
        )
        stored = self._repository.register_frequency_calibration_set(registration)
        return AuthoritativeCalibrationPublication(
            publication=publication,
            calibration_set=_set_contract(stored.registration),
        )

    def lookup(self, promotion_id: str) -> AuthoritativeCalibrationPublication:
        stored = self._repository.frequency_calibration_set_by_promotion_id(promotion_id)
        registration = stored.registration
        publication = DurableCalibrationPublicationRefV1(
            promotion_id=registration.promotion_id,
            bundle_uri=registration.evidence_uri,
            manifest_digest=registration.evidence_digest,
            sealed_utc_ns=registration.sealed_utc_ns,
        )
        authoritative = self._authoritative.resolve(publication)
        catalog_value = _set_contract(registration)
        if authoritative != catalog_value:
            raise ValueError("calibration catalog differs from durable promotion readback")
        return AuthoritativeCalibrationPublication(
            publication=publication,
            calibration_set=catalog_value,
        )

    def resolve(self, identity: ReceiverPathIdentityV1) -> ResolvedFrequencyCalibration:
        resolved = self._repository.resolve_frequency_calibration(
            radio_serial=identity.radio_serial,
            receiver_id=identity.receiver_id,
            physical_receiver_id=identity.physical_receiver_id,
            hardware_epoch_id=identity.hardware_epoch_id,
            capture_start_utc_ns=identity.capture_utc_ns,
            capture_end_utc_ns=identity.capture_end_utc_ns,
        )
        calibration = ReceiverFrequencyCalibrationV1.model_validate(
            _calibration_document(resolved.calibration.registration)
        )
        calibration_set = _set_contract(resolved.calibration_set.registration)
        if not calibration.matches(identity):
            raise ValueError("resolved catalog calibration mismatches receiver identity")
        return ResolvedFrequencyCalibration(
            calibration=calibration,
            calibration_set=calibration_set,
        )

def _calibration_registration(
    value: ReceiverFrequencyCalibrationV1,
    evidence_uri: str,
    evidence_digest: str,
) -> FrequencyCalibrationRegistration:
    return FrequencyCalibrationRegistration(
        calibration_id=value.calibration_id,
        calibration_digest=value.calibration_digest,
        radio_id=value.radio_id,
        radio_serial=value.radio_serial,
        receiver_id=value.receiver_id,
        physical_receiver_id=value.physical_receiver_id,
        hardware_epoch_id=value.hardware_epoch_id,
        center_hz=value.center_hz,
        uncertainty_lower_hz=value.uncertainty_lower_hz,
        uncertainty_upper_hz=value.uncertainty_upper_hz,
        valid_from_utc_ns=value.valid_from_utc_ns,
        valid_until_utc_ns=value.valid_until_utc_ns,
        method=value.method,
        created_utc_ns=value.created_utc_ns,
        evidence_uri=evidence_uri,
        evidence_digest=evidence_digest,
        evidence=tuple(item.model_dump(mode="json") for item in value.evidence),
    )


def _calibration_document(value: FrequencyCalibrationRegistration) -> dict[str, object]:
    return {
        "schema_version": 1,
        "calibration_id": value.calibration_id,
        "calibration_digest": value.calibration_digest,
        "radio_id": value.radio_id,
        "radio_serial": value.radio_serial,
        "receiver_id": value.receiver_id,
        "physical_receiver_id": value.physical_receiver_id,
        "hardware_epoch_id": value.hardware_epoch_id,
        "center_hz": value.center_hz,
        "uncertainty_lower_hz": value.uncertainty_lower_hz,
        "uncertainty_upper_hz": value.uncertainty_upper_hz,
        "valid_from_utc_ns": value.valid_from_utc_ns,
        "valid_until_utc_ns": value.valid_until_utc_ns,
        "method": value.method,
        "created_utc_ns": value.created_utc_ns,
        "evidence": value.evidence,
    }


def _set_contract(value: FrequencyCalibrationSetRegistration) -> ReceiverFrequencyCalibrationSetV1:
    return ReceiverFrequencyCalibrationSetV1.model_validate(
        {
            "schema_version": 1,
            "calibration_set_id": value.set_id,
            "calibration_set_digest": value.set_digest,
            "calibrations": tuple(
                _calibration_document(calibration) for calibration in value.calibrations
            ),
        }
    )
