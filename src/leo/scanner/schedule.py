"""Immutable schedule and run evidence for the long-form scanner."""

from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Annotated, Literal, Self

from pydantic import Field, StringConstraints, model_validator

from leo.contracts.digests import Sha256Digest, canonical_digest
from leo.scanner.models import (
    ScannerCloseFailureEvidenceV1,
    ScannerConfigurationV3,
    ScannerModel,
    scheduled_low_band_targets,
)

SCANNER_RATE_PLAN_V1 = "alternating-2p5m-5m-v1"
SCANNER_RATE_CYCLE_HZ = (2_500_000, 5_000_000)

SafeIdentifier = Annotated[
    str,
    StringConstraints(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$"),
]
OperationKey = Annotated[
    str,
    StringConstraints(min_length=1, max_length=256, pattern=r"^[A-Za-z0-9][A-Za-z0-9:._+-]*$"),
]
ReportFilename = Annotated[
    str,
    StringConstraints(
        min_length=6,
        max_length=255,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*\.json$",
    ),
]
BoundedIdentity = Annotated[str, StringConstraints(min_length=1, max_length=128)]


class ScheduledScannerRunIntentV1(ScannerModel):
    """One fully resolved scanner slot persisted before radio admission."""

    schema_version: Literal[1] = 1
    policy_id: Literal["alternating-2p5m-5m-v1"] = "alternating-2p5m-5m-v1"
    intent_digest: Sha256Digest
    operation_key: OperationKey
    radio_id: SafeIdentifier
    radio_serial: BoundedIdentity
    scheduled_for: datetime
    cadence_ordinal: Annotated[int, Field(ge=0)]
    interval_seconds: Annotated[float, Field(gt=0, le=86_400)]
    maximum_lateness_seconds: Annotated[float, Field(ge=0, le=86_400)]
    run_duration_seconds: Annotated[float, Field(gt=0, le=1_800)]
    configuration: ScannerConfigurationV3

    @model_validator(mode="after")
    def _intent_is_closed(self) -> Self:
        if self.scheduled_for.tzinfo is None or self.scheduled_for.utcoffset() is None:
            raise ValueError("scheduled scanner clock must be timezone-aware")
        scheduled = self.scheduled_for.astimezone(UTC).timestamp()
        expected_ordinal = int(scheduled // self.interval_seconds)
        if self.cadence_ordinal != expected_ordinal or not math.isclose(
            scheduled,
            expected_ordinal * self.interval_seconds,
            rel_tol=0.0,
            abs_tol=1e-6,
        ):
            raise ValueError("scheduled scanner intent is not aligned to its cadence slot")
        expected_rate = SCANNER_RATE_CYCLE_HZ[self.cadence_ordinal % len(SCANNER_RATE_CYCLE_HZ)]
        if (
            self.configuration.sample_rate_hz != expected_rate
            or self.configuration.bandwidth_hz != expected_rate
        ):
            raise ValueError("scheduled scanner rate and bandwidth disagree with the slot")
        if self.intent_digest != scheduled_scanner_run_intent_digest(self):
            raise ValueError("scheduled scanner intent digest does not match content")
        return self


def scheduled_scanner_run_intent_digest(intent: ScheduledScannerRunIntentV1) -> str:
    return canonical_digest(intent.model_dump(mode="json", exclude={"intent_digest"}))


def compile_scheduled_scanner_run_intent_v1(
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
) -> ScheduledScannerRunIntentV1:
    """Resolve one UTC cadence slot to an immutable rate and RF geometry."""

    if scheduled_for.tzinfo is None or scheduled_for.utcoffset() is None:
        raise ValueError("scheduled scanner clock must be timezone-aware")
    canonical = scheduled_for.astimezone(UTC)
    cadence_ordinal = int(canonical.timestamp() // interval_seconds)
    sample_rate_hz = SCANNER_RATE_CYCLE_HZ[cadence_ordinal % len(SCANNER_RATE_CYCLE_HZ)]
    configuration = ScannerConfigurationV3(
        sample_rate_hz=sample_rate_hz,
        bandwidth_hz=sample_rate_hz,
        dwell_ms=dwell_ms,
        gain_db=gain_db,
        glrt64_margin_gate=margin_gate,
        maximum_acquisition_candidates=maximum_acquisition_candidates,
        targets=scheduled_low_band_targets(bandwidth_hz=sample_rate_hz),
    )
    candidate = ScheduledScannerRunIntentV1.model_construct(
        intent_digest="sha256:" + "0" * 64,
        operation_key=operation_key,
        radio_id=radio_id,
        radio_serial=radio_serial,
        scheduled_for=canonical,
        cadence_ordinal=cadence_ordinal,
        interval_seconds=interval_seconds,
        maximum_lateness_seconds=maximum_lateness_seconds,
        run_duration_seconds=run_duration_seconds,
        configuration=configuration,
    )
    document = candidate.model_dump(mode="json", exclude={"intent_digest"})
    return ScheduledScannerRunIntentV1.model_validate(
        {**document, "intent_digest": canonical_digest(document)}
    )


class ScannerRunSweepEntryV1(ScannerModel):
    """One sweep outcome within a bounded-memory scanner run."""

    schema_version: Literal[1] = 1
    scan_id: SafeIdentifier
    capture_elapsed_ms: Annotated[float, Field(ge=0)]
    iq_bundle_uri: str | None = None
    iq_manifest_sha256: Sha256Digest | None = None
    report_filename: ReportFilename | None = None

    @model_validator(mode="after")
    def _bundle_reference_is_complete(self) -> Self:
        if (self.iq_bundle_uri is None) != (self.iq_manifest_sha256 is None):
            raise ValueError("scanner run sweep has a partial IQ bundle reference")
        return self


class ScannerRunManifestV1(ScannerModel):
    """Terminal run evidence referencing independently committed sweep bundles."""

    schema_version: Literal[1] = 1
    kind: Literal["starlink_scanner_run"] = "starlink_scanner_run"
    run_id: SafeIdentifier
    intent: ScheduledScannerRunIntentV1
    radio_id: str
    radio_serial: str
    radio_uri: str
    started_utc_ns: Annotated[int, Field(ge=0)]
    finalized_utc_ns: Annotated[int, Field(ge=0)]
    capture_elapsed_ms: Annotated[float, Field(ge=0)]
    status: Literal["complete", "cancelled", "failed"]
    stop_reason: str
    sweeps: tuple[ScannerRunSweepEntryV1, ...]
    close_failure: ScannerCloseFailureEvidenceV1 | None = None

    @model_validator(mode="after")
    def _run_is_consistent(self) -> Self:
        if self.finalized_utc_ns < self.started_utc_ns:
            raise ValueError("scanner run finalization precedes its start")
        if len({item.scan_id for item in self.sweeps}) != len(self.sweeps):
            raise ValueError("scanner run sweep IDs must be unique")
        if self.radio_id != self.intent.radio_id or self.radio_serial != self.intent.radio_serial:
            raise ValueError("scanner run radio identity disagrees with its scheduled intent")
        if self.status == "complete" and (not self.sweeps or self.close_failure is not None):
            raise ValueError("complete scanner run lacks sweeps or has a close failure")
        return self
