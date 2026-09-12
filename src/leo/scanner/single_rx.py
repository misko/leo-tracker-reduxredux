"""Versioned 10-MS/s single-receiver scanner geometry and durable selection."""

from __future__ import annotations

import hashlib
import math
from datetime import UTC, datetime
from typing import Any, Literal, Self

from pydantic import Field, field_validator, model_validator

from leo.contracts.digests import canonical_digest
from leo.scanner.models import ScannerConfigurationV3, scheduled_low_band_targets
from leo.scanner.persistent_hop import (
    PersistentHopPlanV1,
    PersistentHopProfileV1,
    PersistentHopSessionReceiptV1,
    PersistentHopUtcTimingAuthorityV1,
)
from leo.scanner.schedule import (
    ScheduledScannerRunIntentV1,
    canonical_scheduled_scanner_operation_key,
)

SINGLE_RX_PROFILE_ID = "single-rx-random-10m-300s-v1"
SINGLE_RX_RATE_HZ: Literal[10_000_000] = 10_000_000


def parse_scheduled_scanner_intent(payload: dict) -> ScheduledScannerRunIntentV1:
    model = (
        SingleRxScheduledScannerIntentV2
        if payload.get("schema_version") == 2
        else ScheduledScannerRunIntentV1
    )
    return model.model_validate(payload)


def single_rx_for_operation(operation_key: str, radio_serial: str) -> Literal[0, 1]:
    """A uniform pseudorandom choice keyed by the durable scan identity.

    Unlike process RNG state, this selection survives queue retries and races.
    The domain separator makes it independent of all other scheduling choices.
    """

    payload = f"{SINGLE_RX_PROFILE_ID}\0{radio_serial}\0{operation_key}".encode()
    return 1 if hashlib.sha256(payload).digest()[0] & 1 else 0


def _validate_physical_receiver(value: Any) -> Any:
    if not isinstance(value, (tuple, list)) or len(value) != 1 or type(value[0]) is not int:
        raise ValueError("single-RX selection requires one exact integer receiver ID")
    return value


class SingleRxScannerConfigurationV4(ScannerConfigurationV3):
    """Pilot-centred 10 MHz; physical receiver ID is not a payload column."""

    schema_version: Literal[4] = 4  # type: ignore[assignment]
    band_plan_id: Literal["starlink-low-ch1-ch4-pilot-centered-single-rx-v1"] = (  # type: ignore[assignment]
        "starlink-low-ch1-ch4-pilot-centered-single-rx-v1"  # type: ignore[assignment]
    )
    sample_rate_hz: Literal[10_000_000] = SINGLE_RX_RATE_HZ
    bandwidth_hz: Literal[10_000_000] = SINGLE_RX_RATE_HZ
    receiver_ids: tuple[Literal[0]] | tuple[Literal[1]] = Field(...)
    dwell_ms: Literal[120] = 120

    @field_validator("receiver_ids", mode="before")
    @classmethod
    def _physical_receiver_is_exact(cls, value):
        return _validate_physical_receiver(value)

    @model_validator(mode="after")
    def _geometry_is_exact(self) -> Self:
        if not math.isfinite(self.gain_db):
            raise ValueError("single-RX scanner gain must be finite")
        if self.targets != scheduled_low_band_targets(
            bandwidth_hz=5_000_000, lnb_lo_hz=self.lnb_lo_hz
        ):
            raise ValueError("single-RX scanner targets must remain pilot-centred")
        return self


class SingleRxScheduledScannerIntentV2(ScheduledScannerRunIntentV1):
    schema_version: Literal[2] = 2  # type: ignore[assignment]
    policy_id: Literal["single-rx-random-10m-300s-v1"] = SINGLE_RX_PROFILE_ID  # type: ignore[assignment]
    run_duration_seconds: Literal[300] = 300
    configuration: SingleRxScannerConfigurationV4

    @model_validator(mode="after")
    def _intent_is_closed(self) -> Self:
        if self.scheduled_for.tzinfo is None or self.scheduled_for.utcoffset() is None:
            raise ValueError("scheduled scanner clock must be timezone-aware")
        if self.interval_seconds != 1200 or self.operation_key != (
            canonical_scheduled_scanner_operation_key(self.scheduled_for)
        ):
            raise ValueError("single-RX intent requires a canonical 20-minute operation")
        seconds = self.scheduled_for.astimezone(UTC).timestamp()
        if self.cadence_ordinal != int(seconds // self.interval_seconds) or not math.isclose(
            seconds, self.cadence_ordinal * self.interval_seconds, rel_tol=0, abs_tol=1e-6
        ):
            raise ValueError("single-RX scanner intent is not aligned to its cadence slot")
        if self.configuration.receiver_ids != (
            single_rx_for_operation(self.operation_key, self.radio_serial),
        ):
            raise ValueError("single-RX choice disagrees with durable operation identity")
        if self.intent_digest != canonical_digest(
            self.model_dump(mode="json", exclude={"intent_digest"})
        ):
            raise ValueError("single-RX intent digest does not match content")
        return self


def compile_single_rx_scanner_intent(
    *,
    operation_key: str,
    radio_id: str,
    radio_serial: str,
    scheduled_for: datetime,
    interval_seconds: float,
    maximum_lateness_seconds: float,
    run_duration_seconds: float,
    dwell_ms: int,
    gain_db: float,
    margin_gate: float,
    maximum_acquisition_candidates: int,
) -> SingleRxScheduledScannerIntentV2:
    if run_duration_seconds != 300 or dwell_ms != 120:
        raise ValueError("single-RX profile requires 300 seconds and 120 ms visits")
    if scheduled_for.tzinfo is None or scheduled_for.utcoffset() is None:
        raise ValueError("scheduled scanner clock must be timezone-aware")
    canonical = scheduled_for.astimezone(UTC)
    receiver_ids: tuple[Literal[0]] | tuple[Literal[1]] = (
        (1,) if single_rx_for_operation(operation_key, radio_serial) else (0,)
    )
    configuration = SingleRxScannerConfigurationV4(
        receiver_ids=receiver_ids,
        gain_db=gain_db,
        glrt64_margin_gate=margin_gate,
        maximum_acquisition_candidates=maximum_acquisition_candidates,
        targets=scheduled_low_band_targets(bandwidth_hz=5_000_000),
    )
    candidate = SingleRxScheduledScannerIntentV2.model_construct(
        intent_digest="sha256:" + "0" * 64,
        operation_key=operation_key,
        radio_id=radio_id,
        radio_serial=radio_serial,
        scheduled_for=canonical,
        cadence_ordinal=int(canonical.timestamp() // interval_seconds),
        interval_seconds=interval_seconds,
        maximum_lateness_seconds=maximum_lateness_seconds,
        configuration=configuration,
    )
    document = candidate.model_dump(mode="json", exclude={"intent_digest"})
    return SingleRxScheduledScannerIntentV2.model_validate(
        {**document, "intent_digest": canonical_digest(document)}
    )


class SingleRxPersistentHopPlanV2(PersistentHopPlanV1):
    schema_version: Literal[2] = 2  # type: ignore[assignment]
    sample_rate_hz: Literal[10_000_000] = SINGLE_RX_RATE_HZ  # type: ignore[assignment]
    bandwidth_hz: Literal[10_000_000] = SINGLE_RX_RATE_HZ  # type: ignore[assignment]
    receiver_ids: tuple[Literal[0]] | tuple[Literal[1]] = Field(...)  # type: ignore[assignment]

    _physical_receiver_is_exact = field_validator("receiver_ids", mode="before")(
        _validate_physical_receiver
    )

    @model_validator(mode="after")
    def _geometry_is_exact(self) -> Self:
        if not math.isfinite(self.gain_db):
            raise ValueError("single-RX gain must be finite")
        if self.transition_guard_samples >= self.valid_visit_samples:
            raise ValueError("single-RX transition guard exceeds its valid visit")
        if self.planned_valid_duty_ppm < self.minimum_valid_duty_ppm:
            raise ValueError("single-RX guard cannot meet the minimum valid duty")
        expected = tuple(
            PersistentHopProfileV1(target_index=i, fastlock_profile_index=i, target=target)
            for i, target in enumerate(scheduled_low_band_targets(bandwidth_hz=5_000_000))
        )
        if self.profiles != expected:
            raise ValueError("single-RX hopping profiles must remain pilot-centred")
        return self


class SingleRxHopReceiptV2(PersistentHopSessionReceiptV1):
    schema_version: Literal[2] = 2  # type: ignore[assignment]
    plan: SingleRxPersistentHopPlanV2


class SingleRxHopTimingV2(PersistentHopUtcTimingAuthorityV1):
    schema_version: Literal[2] = 2  # type: ignore[assignment]
    sample_rate_hz: Literal[10_000_000] = SINGLE_RX_RATE_HZ  # type: ignore[assignment]


def compile_single_rx_hop_plan(
    intent: ScheduledScannerRunIntentV1,
    *,
    transition_guard_us: int = 1000,
    kernel_buffers: int = 8,
    samples_per_block: int = 131_072,
) -> SingleRxPersistentHopPlanV2:
    if not isinstance(intent, SingleRxScheduledScannerIntentV2):
        raise ValueError("single-RX hop compilation requires a V2 single-RX intent")
    config = intent.configuration
    return SingleRxPersistentHopPlanV2(
        receiver_ids=config.receiver_ids,
        gain_db=config.gain_db,
        transition_guard_samples=SINGLE_RX_RATE_HZ * transition_guard_us // 1_000_000,
        kernel_buffers=kernel_buffers,
        samples_per_block=samples_per_block,
        profiles=tuple(
            PersistentHopProfileV1(target_index=i, fastlock_profile_index=i, target=target)
            for i, target in enumerate(config.targets)
        ),
    )
