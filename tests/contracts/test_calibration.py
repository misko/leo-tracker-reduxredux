from __future__ import annotations

import pytest
from pydantic import ValidationError

from leo.contracts import (
    CalibrationEvidenceV1,
    ReceiverFrequencyCalibrationSetV1,
    ReceiverFrequencyCalibrationV1,
    ReceiverPathIdentityV1,
)


def _calibration(*, start: int = 100, until: int | None = 200, center: float = 125.0):
    return ReceiverFrequencyCalibrationV1.create(
        calibration_id=f"cal-{start}",
        radio_id="radio-a",
        radio_serial="serial-a",
        receiver_id=1,
        physical_receiver_id="radio-a-rx1",
        center_hz=center,
        uncertainty_lower_hz=center - 2,
        uncertainty_upper_hz=center + 3,
        valid_from_utc_ns=start,
        valid_until_utc_ns=until,
        method="reviewed-blind-pilot-center-v1",
        created_utc_ns=50,
        evidence=(
            CalibrationEvidenceV1(
                kind="analysis-receipt",
                uri="artifact://calibration/radio-a-rx1.json",
                digest="sha256:" + "1" * 64,
                source_revision="native-pilot-v1",
            ),
        ),
    )


def _identity(at: int) -> ReceiverPathIdentityV1:
    return ReceiverPathIdentityV1(
        radio_id="radio-a",
        radio_serial="serial-a",
        receiver_id=1,
        physical_receiver_id="radio-a-rx1",
        capture_utc_ns=at,
    )


def test_calibration_digest_is_canonical_and_tamper_evident() -> None:
    calibration = _calibration()
    assert calibration == _calibration()
    document = calibration.model_dump(mode="json")
    document["center_hz"] = 126.0
    with pytest.raises(ValidationError, match="digest does not match"):
        ReceiverFrequencyCalibrationV1.model_validate(document)


def test_validity_is_half_open_and_expired_calibration_does_not_resolve() -> None:
    first = _calibration(start=100, until=200)
    second = _calibration(start=200, until=300, center=130)
    calibrations = ReceiverFrequencyCalibrationSetV1.create(
        calibration_set_id="reviewed-set-v1",
        calibrations=(second, first),
    )

    assert calibrations.resolve(_identity(199)) == first
    assert calibrations.resolve(_identity(200)) == second
    assert calibrations.resolve(_identity(300)) is None
    assert calibrations.calibrations == (first, second)


def test_calibration_set_rejects_overlapping_or_open_ended_intervals() -> None:
    with pytest.raises(ValidationError, match="overlap"):
        ReceiverFrequencyCalibrationSetV1.create(
            calibration_set_id="overlap",
            calibrations=(_calibration(start=100, until=210), _calibration(start=200, until=300)),
        )
    with pytest.raises(ValidationError, match="overlap"):
        ReceiverFrequencyCalibrationSetV1.create(
            calibration_set_id="open-overlap",
            calibrations=(_calibration(start=100, until=None), _calibration(start=300, until=400)),
        )


def test_calibration_requires_nonempty_evidence_and_nonempty_interval() -> None:
    values = _calibration().model_dump(mode="python")
    values["evidence"] = ()
    with pytest.raises(ValidationError, match="evidence"):
        ReceiverFrequencyCalibrationV1.model_validate(values)
    with pytest.raises(ValidationError, match="non-empty"):
        _calibration(start=100, until=100)
