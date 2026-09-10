"""Application validation of the public native-journal recording interchange.

This port depends only on its documented JSON contract, never the radio
repository's implementation. It does not establish radio/boot provenance.
"""

from __future__ import annotations

from fractions import Fraction
from ipaddress import IPv4Address
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import ConfigDict, Field, model_validator

from leo.contracts.base import ContractModel

U32 = Annotated[int, Field(ge=0, lt=2**32)]
Identity = Annotated[int, Field(gt=0, lt=2**32)]
DecimalInteger = Annotated[str, Field(pattern=r"^(0|[1-9][0-9]*|-[1-9][0-9]*)$")]
Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class _NativePort(ContractModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, allow_inf_nan=False)


def integer(value: str, bits: int, *, signed: bool = False) -> int:
    number = int(value)
    lower, upper = (-(2 ** (bits - 1)), 2 ** (bits - 1)) if signed else (0, 2**bits)
    if not lower <= number < upper:
        raise ValueError("native integer exceeds its declared width")
    return number


class NativeJournalSnapshotV1(_NativePort):
    generation: Identity
    epoch: Identity
    latest_index: DecimalInteger
    status: Annotated[int, Field(ge=0, lt=256)]
    faults: Annotated[int, Field(ge=0, lt=16)]
    configured: U32
    admitted: U32
    late: U32
    no_space: U32
    unavailable: U32
    expired: U32
    cancelled: U32
    committed: U32
    popped: U32
    queued: Literal[0]
    high_water: Annotated[int, Field(ge=0, le=64)]
    cdc_drops: U32
    pacer_drops: U32

    @model_validator(mode="after")
    def _closed(self) -> Self:
        integer(self.latest_index, 64)
        if self.status & 4 or not self.admitted == self.committed == self.popped:
            raise ValueError("native snapshot has outstanding work")
        if self.configured != sum(
            (
                self.admitted,
                self.late,
                self.no_space,
                self.unavailable,
                self.expired,
                self.cancelled,
            )
        ):
            raise ValueError("native opportunity accounting does not close")
        return self


class NativeJournalDescriptorV1(_NativePort):
    first_frame: Annotated[int, Field(ge=0, lt=225000)]
    epoch: Identity
    tag: Identity
    start_sample: DecimalInteger
    start_fraction_q16: Annotated[int, Field(ge=0, lt=2**16)]
    period_q16: Annotated[int, Field(ge=79328 * 65536, le=81000 * 65536)]
    phase_step_q32_16: Annotated[int, Field(ge=0, lt=2**48)]
    phase_delta_q32_16: Annotated[int, Field(ge=0, lt=2**48)]
    phase_seed_q32: U32
    repeats: Annotated[int, Field(ge=1, le=64)]
    expires_sample: DecimalInteger

    def prediction(self, repeat: int) -> tuple[int, int]:
        start = round(
            Fraction(
                int(self.start_sample) * 65536 + self.start_fraction_q16 + repeat * self.period_q16,
                65536,
            )
        )
        phase = (
            round(
                Fraction((self.phase_step_q32_16 + repeat * self.phase_delta_q32_16) % 2**48, 65536)
            )
            % 2**32
        )
        return start, phase

    @model_validator(mode="after")
    def _bounded(self) -> Self:
        start = integer(self.start_sample, 64)
        expiry = integer(self.expires_sample, 64)
        if (
            start < 512
            or self.first_frame + self.repeats > 225000
            or self.prediction(self.repeats - 1)[0] + 79199 > expiry
        ):
            raise ValueError("native descriptor exceeds bounded source support")
        return self


class NativeJournalMeasurementV1(_NativePort):
    epoch: Identity
    sequence: U32
    frame: Annotated[int, Field(ge=0, lt=225000)]
    delay_s: float
    residual_hz: float
    cfo_hz: float
    coherence: float
    linearized_coherence: float
    rejection: Annotated[int, Field(ge=0, lt=128)]
    supported: bool
    tag: Identity
    repeat: Annotated[int, Field(ge=0, lt=64)]
    native_start_sample: DecimalInteger
    phase_seed_q32: U32
    phase_step_q32: U32
    sample_count: Annotated[int, Field(ge=0, le=79200)]
    hardware_fault: Annotated[int, Field(ge=0, lt=1024)]
    reference_sum: tuple[DecimalInteger, DecimalInteger]
    delay_sum: tuple[DecimalInteger, DecimalInteger]
    reference_prefix_integral: tuple[DecimalInteger, DecimalInteger]
    observed_energy: DecimalInteger

    @model_validator(mode="after")
    def _evidence(self) -> Self:
        start = integer(self.native_start_sample, 64)
        for value in (*self.reference_sum, *self.delay_sum):
            integer(value, 52, signed=True)
        for value in self.reference_prefix_integral:
            integer(value, 69, signed=True)
        integer(self.observed_energy, 53)
        if self.sample_count and start + self.sample_count - 1 >= 2**64:
            raise ValueError("native arithmetic interval overflows")
        if not self.sample_count and any(
            map(
                int,
                (
                    *self.reference_sum,
                    *self.delay_sum,
                    *self.reference_prefix_integral,
                    self.observed_energy,
                ),
            )
        ):
            raise ValueError("empty native arithmetic has nonzero moments")
        if not self.hardware_fault and self.sample_count != 79200:
            raise ValueError("incomplete native arithmetic lacks a fault")
        if self.supported != (self.rejection == 0) or (
            self.supported and (self.hardware_fault or self.sample_count != 79200)
        ):
            raise ValueError("native support claim contradicts arithmetic or rejection")
        return self


class NativeJournalRecordingV1(_NativePort):
    schema_name: Literal["starlink-glrt-native-journal-recording/v1"] = Field(alias="schema")
    journal_sha256: Digest
    journal_bytes: Annotated[int, Field(ge=6, le=128 * 1024 * 1024)]
    epoch: Identity
    epoch_scope: Literal["journal_local_requires_radio_boot_binding"]
    source_rate_hz: Literal[60000000]
    pilot_samples: Literal[79200]
    pilot_center_offset_samples_twice: Literal[79199]
    timing_rule: Literal["native_start_sample + delay_s * source_rate_hz"]
    frequency_reference: Literal["receiver_relative_uncalibrated"]
    timing_reference: Literal["native_pilot_template"]
    association_and_closure_verified: Literal[True]
    solver_replayed: Literal[False]
    original_native_iq_verified: Literal[False]
    acquisition_verified: Literal[False]
    physical_precision_qualified: Literal[False]
    descriptor_semantics: Literal["retained_intent_execution_accounted_by_heads_and_drained"]
    head_count: Annotated[int, Field(ge=0, le=225000)]
    supported_count: Annotated[int, Field(ge=0, le=225000)]
    rejected_count: Annotated[int, Field(ge=0, le=225000)]
    descriptors: tuple[NativeJournalDescriptorV1, ...]
    measurements: tuple[NativeJournalMeasurementV1, ...]
    drained: NativeJournalSnapshotV1
    final: NativeJournalSnapshotV1

    @model_validator(mode="after")
    def _associated(self) -> Self:
        if not self.epoch == self.drained.epoch == self.final.epoch:
            raise ValueError("native recording crosses source epochs")
        if self.final.configured or self.final.faults or self.final.status & 16:
            raise ValueError("native recording lacks final clearance")
        if not self.head_count == len(self.measurements) == self.drained.popped:
            raise ValueError("native recording head inventory differs")
        if (
            self.supported_count != sum(m.supported for m in self.measurements)
            or self.rejected_count != self.head_count - self.supported_count
        ):
            raise ValueError("native recording fit accounting differs")
        owners = {}
        next_frame = 0
        for descriptor in self.descriptors:
            if (
                descriptor.epoch != self.epoch
                or descriptor.tag in owners
                or descriptor.first_frame != next_frame
            ):
                raise ValueError("native recording descriptor ownership differs")
            owners[descriptor.tag] = descriptor
            next_frame += descriptor.repeats
        if self.drained.configured > next_frame:
            raise ValueError("native configured work exceeds retained descriptor ownership")
        previous = -1
        for sequence, measurement in enumerate(self.measurements):
            owner = owners.get(measurement.tag)
            if (
                owner is None
                or measurement.epoch != self.epoch
                or measurement.sequence != sequence
                or measurement.frame <= previous
                or measurement.frame >= self.drained.configured
                or measurement.repeat >= owner.repeats
                or measurement.frame != owner.first_frame + measurement.repeat
            ):
                raise ValueError("native recording frame association differs")
            if (
                owner.prediction(measurement.repeat)
                != (int(measurement.native_start_sample), measurement.phase_step_q32)
                or measurement.phase_seed_q32 != owner.phase_seed_q32
            ):
                raise ValueError("native recording sample or carrier association differs")
            previous = measurement.frame
        return self


class NativeJournalSourceBindingV1(_NativePort):
    """Retained-owner correspondence, distinct from signed hardware attestation."""

    schema_name: Literal["starlink-glrt-native-source-binding/v1"] = Field(alias="schema")
    evidence_mode: Literal["retrospective_retained_owner_correspondence"]
    recording_export_sha256: Digest
    journal_sha256: Digest
    owner_receipt_sha256: Digest
    collector_protocol_sha256: Digest
    collector_summary_sha256: Digest
    collector_final_snapshot_sha256: Digest
    coarse_iq_sha256: Digest
    coarse_iq_bytes: Annotated[int, Field(gt=0, le=3000000000)]
    serial: Annotated[str, Field(min_length=1, max_length=128)]
    host: str
    boot_id: str
    firmware: Annotated[str, Field(min_length=1, max_length=128)]
    fit_sha256: Digest
    visit: Identity
    epoch: Identity
    episode_index: Annotated[int, Field(ge=0, lt=2)]
    source_rate_hz: Literal[60000000]
    output_rate_hz: Literal[2500000]
    output_samples: Annotated[int, Field(gt=0, le=750000000)]
    native_origin: DecimalInteger
    native_last_output_center: DecimalInteger
    native_samples_per_output_sample: Literal[24]
    native_group_delay_samples: Literal[1272]
    runtime_result: Annotated[int, Field(ge=-5, le=0)]
    owner_status: Annotated[str, Field(min_length=1, max_length=128)]
    head_count: Annotated[int, Field(ge=0, le=225000)]
    supported_count: Annotated[int, Field(ge=0, le=225000)]
    source_correspondence_verified: Literal[True]
    radio_signed_attestation: Literal[False]
    acquisition_verified: Literal[False]
    original_native_iq_verified: Literal[False]
    physical_precision_qualified: Literal[False]

    @model_validator(mode="after")
    def _source(self) -> Self:
        host = IPv4Address(self.host)
        if (
            not host.is_private
            or host.is_loopback
            or host.is_link_local
            or host.is_unspecified
            or host.is_multicast
            or str(host) != self.host
        ):
            raise ValueError("native source binding requires a private Ethernet endpoint")
        if self.serial == "1040007c4a94000211000b009186843ef2":
            raise ValueError("native source binding names the excluded receiver")
        if str(UUID(self.boot_id)) != self.boot_id:
            raise ValueError("native source binding has an invalid boot identity")
        origin = integer(self.native_origin, 64)
        last = integer(self.native_last_output_center, 64)
        if (
            origin < 1272
            or origin % 24
            or last != origin + 24 * (self.output_samples - 1)
            or self.coarse_iq_bytes != 4 * self.output_samples
            or self.supported_count > self.head_count
        ):
            raise ValueError("native source binding geometry or inventory differs")
        return self

    def require_recording(self, recording: NativeJournalRecordingV1, *, export_sha256: str) -> None:
        if (
            self.recording_export_sha256 != export_sha256
            or self.journal_sha256 != recording.journal_sha256
            or self.epoch != recording.epoch
            or self.head_count != recording.head_count
            or self.supported_count != recording.supported_count
        ):
            raise ValueError("native source binding belongs to different recording evidence")
        origin, last = int(self.native_origin), int(self.native_last_output_center)
        for measurement in recording.measurements:
            start = int(measurement.native_start_sample)
            if not origin <= start <= start + recording.pilot_samples - 1 <= last:
                raise ValueError("native pilot lies outside its bound coarse source")
