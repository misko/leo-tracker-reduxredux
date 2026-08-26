"""Strict, bundle-bound qualification for contiguous capture rates."""

from __future__ import annotations

from typing import Annotated, Literal, Self, overload

from pydantic import Field, StringConstraints, field_validator, model_validator

from leo.contracts.base import ContractModel
from leo.contracts.digests import Sha256Digest, canonical_digest
from leo.contracts.host_health import (
    QualificationHostHealthEvidenceV1,
    QualificationHostHealthEvidenceV2,
    QualificationHostHealthPolicyV1,
    QualificationHostHealthPolicyV2,
)
from leo.contracts.radio import RadioId, RadioIdentityV1
from leo.contracts.recording import (
    DEVICE_AXIS_STORAGE_POLICY_V1,
    HostIdentityV1,
    ProducerV1,
    RecordingManifestV2,
    RecordingManifestV3,
)
from leo.contracts.states import CaptureState, StreamState, SynchronizationGrade
from leo.contracts.validity import DeviceAxisContentKind

QualificationId = Annotated[
    str,
    StringConstraints(min_length=1, max_length=96, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$"),
]
_ONE_SECOND_NS = 1_000_000_000
_MINIMUM_WRITER_BYTES_PER_SECOND = 72_000_000
_MINIMUM_V4_WRITER_BYTES_PER_SECOND = 100_000_000
_V4_HOST_HEALTH_POLICY = QualificationHostHealthPolicyV1(
    raid_array_name="md127",
    disk_path="/srv/bulk",
    minimum_available_memory_bytes=32 * 1024**3,
    minimum_free_disk_bytes=1024**4,
)
_V5_HOST_HEALTH_POLICY = QualificationHostHealthPolicyV2(
    raid_array_name="md127",
    disk_path="/srv/bulk",
    required_disk_mount_source="/dev/mapper/vg_bulk-bulk",
    minimum_available_memory_bytes=32 * 1024**3,
    minimum_free_disk_bytes=1024**4,
)


class ContiguousRateQualificationPolicyV1(ContractModel):
    """Lossless two-radio requirements for one exact rate and runtime identity."""

    schema_version: Literal[1] = 1
    required_trial_count: Annotated[int, Field(gt=0)] = 10
    minimum_overlap_fraction: Annotated[float, Field(ge=0, le=1)] = 0.99
    required_kernel_buffers: Annotated[int, Field(ge=2, le=64)] = 8
    required_queue_capacity_refills: Annotated[int, Field(ge=1, le=256)] = 32
    maximum_queue_high_water_fraction: Annotated[float, Field(gt=0, le=1)] = 0.75
    required_metadata_abi_version: Annotated[int, Field(ge=1)] = 1
    maximum_refill_service_interval_ns: Annotated[int | None, Field(gt=0)] = None
    required_tags: tuple[str, ...] = ("CAPTURE_ONLY",)

    @field_validator("required_tags")
    @classmethod
    def _tags_are_canonical(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value or tuple(sorted(set(value))) != value:
            raise ValueError("required qualification tags must be non-empty, unique, and sorted")
        return value


class ContiguousRateRadioMetricsV1(ContractModel):
    """Exact counter-derived continuity metrics for one prerequisite radio arm."""

    schema_version: Literal[1] = 1
    radio_id: RadioId
    requested_sample_count: Annotated[int, Field(gt=0)]
    observed_sample_count: Annotated[int, Field(ge=0)]
    device_span_sample_count: Annotated[int, Field(ge=0)]
    observed_gap_count: Annotated[int, Field(ge=0)]
    observed_missing_sample_count: Annotated[int, Field(ge=0)]
    observed_overflow_count: Annotated[int, Field(ge=0)]
    enqueue_failure_count: Annotated[int, Field(ge=0)]

    def closes_losslessly(self, expected_sample_count: int) -> bool:
        return (
            self.requested_sample_count
            == self.observed_sample_count
            == self.device_span_sample_count
            == expected_sample_count
            and self.observed_gap_count == 0
            and self.observed_missing_sample_count == 0
            and self.observed_overflow_count == 0
            and self.enqueue_failure_count == 0
        )


class ContiguousRateRadioSafetyEvidenceV1(ContractModel):
    """Sealed pre/post safety evidence for one exact radio."""

    schema_version: Literal[1] = 1
    radio_id: RadioId
    pre_safety_evidence_sha256: Sha256Digest
    post_safety_evidence_sha256: Sha256Digest
    pre_tx_safe: bool
    post_tx_safe: bool
    rx_settings_restored: bool
    passed: bool

    @model_validator(mode="after")
    def _pass_matches_safety_observations(self) -> Self:
        expected = self.pre_tx_safe and self.post_tx_safe and self.rx_settings_restored
        if self.passed != expected:
            raise ValueError("radio safety pass flag disagrees with pre/post evidence")
        return self


class ContiguousRateNativeIpCanaryEvidenceV1(ContractModel):
    """One exact one-second counter-authoritative native-IP canary."""

    schema_version: Literal[1] = 1
    transport: Literal["iio_ip"] = "iio_ip"
    duration_ns: Literal[1_000_000_000] = 1_000_000_000
    sample_rate_hz: Annotated[int, Field(gt=0)]
    bandwidth_hz: Annotated[int, Field(gt=0)]
    evidence_sha256: Sha256Digest
    metrics: ContiguousRateRadioMetricsV1
    passed: bool

    @model_validator(mode="after")
    def _pass_matches_one_second_continuity(self) -> Self:
        expected = self.metrics.closes_losslessly(self.sample_rate_hz)
        if self.passed != expected:
            raise ValueError("native-IP canary pass flag disagrees with continuity metrics")
        return self


class ContiguousRateUsbControlArmEvidenceV1(ContractModel):
    """One exact 60-second simultaneous two-radio direct-USB control arm."""

    schema_version: Literal[1] = 1
    transport: Literal["iio_usb"] = "iio_usb"
    simultaneous: Literal[True] = True
    duration_ns: Literal[60_000_000_000] = 60_000_000_000
    sample_rate_hz: Annotated[int, Field(gt=0)]
    bandwidth_hz: Annotated[int, Field(gt=0)]
    evidence_sha256: Sha256Digest
    radio_metrics: tuple[ContiguousRateRadioMetricsV1, ContiguousRateRadioMetricsV1]
    passed: bool

    @model_validator(mode="after")
    def _pass_matches_two_radio_continuity(self) -> Self:
        radio_ids = tuple(metric.radio_id for metric in self.radio_metrics)
        if len(set(radio_ids)) != 2:
            raise ValueError("USB control arm requires two unique radio metrics")
        scaled_samples = self.sample_rate_hz * self.duration_ns
        if scaled_samples % _ONE_SECOND_NS:
            raise ValueError("USB control duration must resolve to a whole sample count")
        expected_sample_count = scaled_samples // _ONE_SECOND_NS
        expected = all(
            metric.closes_losslessly(expected_sample_count) for metric in self.radio_metrics
        )
        if self.passed != expected:
            raise ValueError("USB control-arm pass flag disagrees with continuity metrics")
        return self


class ContiguousRateUsbRadioIdentityV2(RadioIdentityV1):
    """Exact direct-USB identity used only by the V2 qualification chain."""

    schema_version: Literal[2] = 2  # type: ignore[assignment]
    transport: Literal["iio_usb"] = "iio_usb"  # type: ignore[assignment]
    firmware_version: Annotated[str, StringConstraints(min_length=1, max_length=128)]

    @model_validator(mode="after")
    def _uri_is_direct_usb(self) -> Self:
        if not self.uri.startswith("usb:"):
            raise ValueError("USB control radio identity must use an exact usb: URI")
        return self


class ContiguousRateUsbRadioRestorationEvidenceV2(ContractModel):
    """Sealed before/after RX-setting restoration evidence for one USB control radio."""

    schema_version: Literal[2] = 2
    radio_id: RadioId
    pre_settings_evidence_sha256: Sha256Digest
    post_settings_evidence_sha256: Sha256Digest
    rx_settings_restored: bool
    passed: bool

    @model_validator(mode="after")
    def _pass_matches_restoration(self) -> Self:
        if self.passed != self.rx_settings_restored:
            raise ValueError("USB radio restoration pass flag disagrees with RX settings evidence")
        return self


class ContiguousRateUsbRadioCaptureIntervalV2(ContractModel):
    """One USB control radio's host-monotonic capture interval."""

    schema_version: Literal[2] = 2
    radio_id: RadioId
    started_monotonic_ns: Annotated[int, Field(ge=0)]
    ended_monotonic_ns: Annotated[int, Field(ge=0)]

    @model_validator(mode="after")
    def _interval_is_positive(self) -> Self:
        if self.ended_monotonic_ns <= self.started_monotonic_ns:
            raise ValueError("USB radio capture interval must have positive duration")
        return self


class ContiguousRateUsbControlArmEvidenceV2(ContractModel):
    """V2 USB control arm bound to independent identities and RX restoration."""

    schema_version: Literal[2] = 2
    transport: Literal["iio_usb"] = "iio_usb"
    simultaneous: Literal[True] = True
    duration_ns: Literal[60_000_000_000] = 60_000_000_000
    sample_rate_hz: Annotated[int, Field(gt=0)]
    bandwidth_hz: Annotated[int, Field(gt=0)]
    evidence_sha256: Sha256Digest
    minimum_overlap_fraction: Annotated[float, Field(ge=0.99, le=0.99)] = 0.99
    radios: tuple[
        ContiguousRateUsbRadioIdentityV2,
        ContiguousRateUsbRadioIdentityV2,
    ]
    capture_intervals: tuple[
        ContiguousRateUsbRadioCaptureIntervalV2,
        ContiguousRateUsbRadioCaptureIntervalV2,
    ]
    radio_restoration: tuple[
        ContiguousRateUsbRadioRestorationEvidenceV2,
        ContiguousRateUsbRadioRestorationEvidenceV2,
    ]
    radio_metrics: tuple[ContiguousRateRadioMetricsV1, ContiguousRateRadioMetricsV1]
    passed: bool

    @model_validator(mode="after")
    def _pass_matches_identity_continuity_and_restoration(self) -> Self:
        radio_ids = tuple(radio.radio_id for radio in self.radios)
        serials = tuple(radio.serial for radio in self.radios)
        if len(set(radio_ids)) != 2 or len(set(serials)) != 2:
            raise ValueError("USB control arm requires two unique exact radio identities")
        interval_ids = tuple(item.radio_id for item in self.capture_intervals)
        restoration_ids = tuple(item.radio_id for item in self.radio_restoration)
        metric_ids = tuple(metric.radio_id for metric in self.radio_metrics)
        if interval_ids != radio_ids or restoration_ids != radio_ids or metric_ids != radio_ids:
            raise ValueError(
                "USB control intervals, restoration, and metrics must match the exact ordered "
                "control radios"
            )
        scaled_samples = self.sample_rate_hz * self.duration_ns
        if scaled_samples % _ONE_SECOND_NS:
            raise ValueError("USB control duration must resolve to a whole sample count")
        expected_sample_count = scaled_samples // _ONE_SECOND_NS
        continuity_passed = all(
            metric.closes_losslessly(expected_sample_count) for metric in self.radio_metrics
        )
        overlap_ns = min(item.ended_monotonic_ns for item in self.capture_intervals) - max(
            item.started_monotonic_ns for item in self.capture_intervals
        )
        overlap_passed = overlap_ns * 100 >= self.duration_ns * 99
        restoration_passed = all(item.passed for item in self.radio_restoration)
        if self.passed != (continuity_passed and overlap_passed and restoration_passed):
            raise ValueError(
                "USB control-arm pass flag disagrees with continuity, overlap, or RX restoration "
                "evidence"
            )
        return self


class ContiguousRateWriterBenchmarkEvidenceV1(ContractModel):
    """Sealed incompressible writer result with reproducible integer throughput."""

    schema_version: Literal[1] = 1
    payload_kind: Literal["incompressible"] = "incompressible"
    evidence_sha256: Sha256Digest
    uncompressed_bytes_written: Annotated[int, Field(gt=0)]
    elapsed_ns: Annotated[int, Field(gt=0)]
    sustained_bytes_per_second: Annotated[int, Field(ge=0)]
    passed: bool

    @model_validator(mode="after")
    def _pass_matches_writer_metrics(self) -> Self:
        measured = self.uncompressed_bytes_written * _ONE_SECOND_NS // self.elapsed_ns
        if self.sustained_bytes_per_second != measured:
            raise ValueError("writer throughput disagrees with byte and elapsed-time metrics")
        expected = measured >= _MINIMUM_WRITER_BYTES_PER_SECOND
        if self.passed != expected:
            raise ValueError("writer benchmark pass flag disagrees with 72 MB/s threshold")
        return self


class ContiguousRatePrerequisitesV1(ContractModel):
    """Complete safety, control, canary, and writer evidence before promotion trials."""

    schema_version: Literal[1] = 1
    radio_safety: tuple[
        ContiguousRateRadioSafetyEvidenceV1,
        ContiguousRateRadioSafetyEvidenceV1,
    ]
    native_ip_canaries: tuple[
        ContiguousRateNativeIpCanaryEvidenceV1,
        ContiguousRateNativeIpCanaryEvidenceV1,
    ]
    usb_control_arm: ContiguousRateUsbControlArmEvidenceV1
    writer_benchmark: ContiguousRateWriterBenchmarkEvidenceV1

    @model_validator(mode="after")
    def _radio_inventory_is_exact_and_ordered(self) -> Self:
        safety_ids = tuple(item.radio_id for item in self.radio_safety)
        canary_ids = tuple(item.metrics.radio_id for item in self.native_ip_canaries)
        usb_ids = tuple(item.radio_id for item in self.usb_control_arm.radio_metrics)
        if any(len(set(items)) != 2 for items in (safety_ids, canary_ids, usb_ids)):
            raise ValueError("rate prerequisites require exactly two unique radios")
        if not safety_ids == canary_ids == usb_ids:
            raise ValueError("rate prerequisite radio inventories or ordering differ")
        return self

    @property
    def radio_ids(self) -> tuple[str, str]:
        return self.radio_safety[0].radio_id, self.radio_safety[1].radio_id


class ContiguousRatePrerequisitesV2(ContractModel):
    """V2 prerequisites with an independently identified and restored USB control pair."""

    schema_version: Literal[2] = 2
    radio_safety: tuple[
        ContiguousRateRadioSafetyEvidenceV1,
        ContiguousRateRadioSafetyEvidenceV1,
    ]
    native_ip_canaries: tuple[
        ContiguousRateNativeIpCanaryEvidenceV1,
        ContiguousRateNativeIpCanaryEvidenceV1,
    ]
    usb_control_arm: ContiguousRateUsbControlArmEvidenceV2
    writer_benchmark: ContiguousRateWriterBenchmarkEvidenceV1

    @model_validator(mode="after")
    def _production_radio_inventory_is_exact_and_ordered(self) -> Self:
        safety_ids = tuple(item.radio_id for item in self.radio_safety)
        canary_ids = tuple(item.metrics.radio_id for item in self.native_ip_canaries)
        if any(len(set(items)) != 2 for items in (safety_ids, canary_ids)):
            raise ValueError("rate prerequisites require exactly two unique production radios")
        if safety_ids != canary_ids:
            raise ValueError("production safety and native-IP radio inventories or ordering differ")
        return self

    @property
    def radio_ids(self) -> tuple[str, str]:
        return self.radio_safety[0].radio_id, self.radio_safety[1].radio_id


class ContiguousRatePrerequisitesV3(ContractModel):
    """Production-native prerequisites without a non-production transport control."""

    schema_version: Literal[3] = 3
    radio_safety: tuple[
        ContiguousRateRadioSafetyEvidenceV1,
        ContiguousRateRadioSafetyEvidenceV1,
    ]
    native_ip_canaries: tuple[
        ContiguousRateNativeIpCanaryEvidenceV1,
        ContiguousRateNativeIpCanaryEvidenceV1,
    ]
    writer_benchmark: ContiguousRateWriterBenchmarkEvidenceV1

    @model_validator(mode="after")
    def _production_radio_inventory_is_exact_and_ordered(self) -> Self:
        safety_ids = tuple(item.radio_id for item in self.radio_safety)
        canary_ids = tuple(item.metrics.radio_id for item in self.native_ip_canaries)
        if any(len(set(items)) != 2 for items in (safety_ids, canary_ids)):
            raise ValueError("rate prerequisites require exactly two unique production radios")
        if safety_ids != canary_ids:
            raise ValueError("production safety and native-IP radio inventories or ordering differ")
        return self

    @property
    def radio_ids(self) -> tuple[str, str]:
        return self.radio_safety[0].radio_id, self.radio_safety[1].radio_id


class ContiguousRateDeviceAxisCharacterizationStreamV1(ContractModel):
    """Verified full-span 5 MS/s closure for one production stream."""

    schema_version: Literal[1] = 1
    radio_id: RadioId
    logical_sample_count: Literal[300_000_000] = 300_000_000
    observed_sample_count: Annotated[int, Field(gt=0, le=300_000_000)]
    zero_fill_sample_count: Annotated[int, Field(ge=0, le=300_000_000)]
    continuity_segment_count: Annotated[int, Field(gt=0)]
    gap_count: Annotated[int, Field(ge=0)]
    missing_sample_count: Annotated[int, Field(ge=0)]
    overflow_count: Annotated[int, Field(ge=0)]
    enqueue_failure_count: Annotated[int, Field(ge=0)]
    terminal_rejected_gap_count: Annotated[int, Field(ge=0)]
    terminal_rejected_missing_sample_count: Annotated[int, Field(ge=0)]
    terminal_rejected_overflow_count: Annotated[int, Field(ge=0)]
    queue_capacity_refills: Literal[32]
    queue_high_water_refills: Annotated[int, Field(ge=1, le=24)]
    gap_map_segment_count: Annotated[int, Field(gt=0)]
    gap_map_boundary_count: Annotated[int, Field(ge=0)]
    validity_segment_count: Annotated[int, Field(gt=0)]
    observed_iq_sha256: Sha256Digest
    logical_iq_sha256: Sha256Digest
    timeline_sha256: Sha256Digest
    gap_map_sha256: Sha256Digest
    validity_inventory_sha256: Sha256Digest

    @model_validator(mode="after")
    def _device_axis_is_closed(self) -> Self:
        if self.observed_sample_count + self.zero_fill_sample_count != self.logical_sample_count:
            raise ValueError("5 MS/s logical span must equal observed plus zero fill")
        if self.missing_sample_count != self.zero_fill_sample_count:
            raise ValueError("5 MS/s missing samples must equal physical zero fill")
        if self.gap_count != self.gap_map_boundary_count:
            raise ValueError("5 MS/s gap count must equal the verified gap-map boundaries")
        if self.gap_map_segment_count != self.validity_segment_count:
            raise ValueError("5 MS/s gap-map and validity segment inventories differ")
        if self.validity_segment_count != self.gap_count + 1:
            raise ValueError("5 MS/s validity segments do not close every gap boundary")
        if self.continuity_segment_count > self.validity_segment_count:
            raise ValueError("5 MS/s continuity segments exceed the validity inventory")
        if (
            self.overflow_count
            or self.enqueue_failure_count
            or self.terminal_rejected_gap_count
            or self.terminal_rejected_missing_sample_count
            or self.terminal_rejected_overflow_count
        ):
            raise ValueError("5 MS/s characterization contains overflow or rejected refills")
        if not self.zero_fill_sample_count and self.observed_iq_sha256 != self.logical_iq_sha256:
            raise ValueError("lossless 5 MS/s logical and observed IQ digests differ")
        return self


class ContiguousRateDeviceAxisCharacterizationV1(ContractModel):
    """Sealed exact-profile 5 MS/s V3 characterization required by V4 cutover."""

    schema_version: Literal[1] = 1
    evidence_sha256: Sha256Digest
    manifest_sha256: Sha256Digest
    session_id: QualificationId
    profile_revision_digest: Sha256Digest
    capture_plan_digest: Sha256Digest
    sample_rate_hz: Literal[5_000_000] = 5_000_000
    bandwidth_hz: Literal[2_500_000] = 2_500_000
    requested_sample_count: Literal[300_000_000] = 300_000_000
    radios: tuple[RadioIdentityV1, RadioIdentityV1]
    host: HostIdentityV1
    producer: ProducerV1
    manifest_state: Literal[CaptureState.COMMITTED, CaptureState.DEGRADED]
    streams: tuple[
        ContiguousRateDeviceAxisCharacterizationStreamV1,
        ContiguousRateDeviceAxisCharacterizationStreamV1,
    ]
    bundle_verified: bool
    physical_zero_verified: bool
    validity_verified: bool
    gap_map_verified: bool
    passed: bool
    errors: tuple[str, ...]

    @model_validator(mode="after")
    def _characterization_is_truthful(self) -> Self:
        radio_ids = tuple(radio.radio_id for radio in self.radios)
        if len(set(radio_ids)) != 2:
            raise ValueError("5 MS/s characterization requires two unique radios")
        if tuple(stream.radio_id for stream in self.streams) != radio_ids:
            raise ValueError("5 MS/s stream evidence order differs from exact radios")
        any_loss = any(stream.zero_fill_sample_count for stream in self.streams)
        expected_state = CaptureState.DEGRADED if any_loss else CaptureState.COMMITTED
        if self.manifest_state is not expected_state:
            raise ValueError("5 MS/s manifest state disagrees with observation loss")
        expected_pass = (
            not self.errors
            and self.bundle_verified
            and self.physical_zero_verified
            and self.validity_verified
            and self.gap_map_verified
        )
        if self.passed != expected_pass:
            raise ValueError("5 MS/s pass flag disagrees with verified characterization evidence")
        return self


class ContiguousRatePrerequisitesV4(ContractModel):
    """V4 production prerequisites with exact host and 5 MS/s evidence."""

    schema_version: Literal[4] = 4
    radio_safety: tuple[
        ContiguousRateRadioSafetyEvidenceV1,
        ContiguousRateRadioSafetyEvidenceV1,
    ]
    native_ip_canaries: tuple[
        ContiguousRateNativeIpCanaryEvidenceV1,
        ContiguousRateNativeIpCanaryEvidenceV1,
    ]
    writer_benchmark: ContiguousRateWriterBenchmarkEvidenceV1
    host_health: QualificationHostHealthEvidenceV1
    five_m_characterization: ContiguousRateDeviceAxisCharacterizationV1

    @model_validator(mode="after")
    def _production_inventory_and_characterization_are_exact(self) -> Self:
        safety_ids = tuple(item.radio_id for item in self.radio_safety)
        canary_ids = tuple(item.metrics.radio_id for item in self.native_ip_canaries)
        characterization_ids = tuple(
            radio.radio_id for radio in self.five_m_characterization.radios
        )
        if any(len(set(items)) != 2 for items in (safety_ids, canary_ids)):
            raise ValueError("rate prerequisites require exactly two unique production radios")
        if not safety_ids == canary_ids == characterization_ids:
            raise ValueError("V4 safety, canary, and 5 MS/s radio inventories differ")
        if any(not evidence.passed for evidence in self.radio_safety):
            raise ValueError("rate qualification requires passing per-radio safety evidence")
        if any(not canary.passed for canary in self.native_ip_canaries):
            raise ValueError("rate qualification requires passing native-IP canaries")
        if (
            not self.writer_benchmark.passed
            or self.writer_benchmark.sustained_bytes_per_second
            < _MINIMUM_V4_WRITER_BYTES_PER_SECOND
        ):
            raise ValueError(
                "V4 rate qualification requires measured incompressible writer throughput "
                "of at least 100 MB/s"
            )
        if self.host_health.policy != _V4_HOST_HEALTH_POLICY:
            raise ValueError(
                "V4 qualification requires the reviewed md127, /srv/bulk, "
                "32 GiB memory, and 1 TiB disk host-health policy"
            )
        if not self.host_health.passed:
            raise ValueError("V4 qualification requires passing pre/post host-health evidence")
        if not self.five_m_characterization.passed:
            raise ValueError("V4 qualification requires passing 5 MS/s characterization")
        return self

    @property
    def radio_ids(self) -> tuple[str, str]:
        return self.radio_safety[0].radio_id, self.radio_safety[1].radio_id


class ContiguousRatePrerequisitesV5(ContractModel):
    """V5 prerequisites with scoped, immutable kernel-I/O history evidence."""

    schema_version: Literal[5] = 5
    radio_safety: tuple[
        ContiguousRateRadioSafetyEvidenceV1,
        ContiguousRateRadioSafetyEvidenceV1,
    ]
    native_ip_canaries: tuple[
        ContiguousRateNativeIpCanaryEvidenceV1,
        ContiguousRateNativeIpCanaryEvidenceV1,
    ]
    writer_benchmark: ContiguousRateWriterBenchmarkEvidenceV1
    host_health: QualificationHostHealthEvidenceV2
    five_m_characterization: ContiguousRateDeviceAxisCharacterizationV1

    @model_validator(mode="after")
    def _production_inventory_and_characterization_are_exact(self) -> Self:
        safety_ids = tuple(item.radio_id for item in self.radio_safety)
        canary_ids = tuple(item.metrics.radio_id for item in self.native_ip_canaries)
        characterization_ids = tuple(
            radio.radio_id for radio in self.five_m_characterization.radios
        )
        if any(len(set(items)) != 2 for items in (safety_ids, canary_ids)):
            raise ValueError("rate prerequisites require exactly two unique production radios")
        if not safety_ids == canary_ids == characterization_ids:
            raise ValueError("V5 safety, canary, and 5 MS/s radio inventories differ")
        if any(not evidence.passed for evidence in self.radio_safety):
            raise ValueError("rate qualification requires passing per-radio safety evidence")
        if any(not canary.passed for canary in self.native_ip_canaries):
            raise ValueError("rate qualification requires passing native-IP canaries")
        if (
            not self.writer_benchmark.passed
            or self.writer_benchmark.sustained_bytes_per_second
            < _MINIMUM_V4_WRITER_BYTES_PER_SECOND
        ):
            raise ValueError(
                "V5 rate qualification requires measured incompressible writer throughput "
                "of at least 100 MB/s"
            )
        if self.host_health.policy != _V5_HOST_HEALTH_POLICY:
            raise ValueError(
                "V5 qualification requires the reviewed md127, /srv/bulk, "
                "32 GiB memory, 1 TiB disk, and exact mount-source host-health policy"
            )
        if not self.host_health.passed:
            raise ValueError("V5 qualification requires passing scoped host-health evidence")
        if not self.five_m_characterization.passed:
            raise ValueError("V5 qualification requires passing 5 MS/s characterization")
        return self

    @property
    def radio_ids(self) -> tuple[str, str]:
        return self.radio_safety[0].radio_id, self.radio_safety[1].radio_id


class ContiguousRateQualificationTargetV1(ContractModel):
    """The exact plan, hardware, and runtime identity being qualified."""

    schema_version: Literal[1] = 1
    qualification_id: QualificationId
    profile_revision_digest: Sha256Digest
    capture_plan_digest: Sha256Digest
    sample_rate_hz: Annotated[int, Field(gt=0)]
    bandwidth_hz: Annotated[int, Field(gt=0)]
    requested_sample_count: Annotated[int, Field(gt=0)]
    expected_radios: tuple[RadioIdentityV1, RadioIdentityV1]
    expected_host: HostIdentityV1
    expected_producer: ProducerV1
    pluto_plus_utils_revision: Annotated[
        str,
        StringConstraints(pattern=r"^[0-9a-f]{40}$"),
    ]
    libiio_version: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    libiio_library_sha256: Sha256Digest
    python_iio_sha256: Sha256Digest
    native_network_interface: Annotated[str, StringConstraints(min_length=1, max_length=64)]
    native_source_address: Annotated[str, StringConstraints(min_length=1, max_length=64)]
    prerequisites: ContiguousRatePrerequisitesV1
    policy: ContiguousRateQualificationPolicyV1 = Field(
        default_factory=ContiguousRateQualificationPolicyV1
    )

    @model_validator(mode="after")
    def _identity_is_promotion_grade(self) -> Self:
        radio_ids = tuple(radio.radio_id for radio in self.expected_radios)
        if len(set(radio_ids)) != 2:
            raise ValueError("contiguous rate qualification requires two unique radios")
        if any(radio.firmware_version is None for radio in self.expected_radios):
            raise ValueError("rate qualification requires exact radio firmware identities")
        if self.expected_host.machine_id is None:
            raise ValueError("rate qualification requires an exact host machine identity")
        if self.expected_producer.source_revision is None:
            raise ValueError("rate qualification requires an exact producer source revision")
        if self.prerequisites.radio_ids != radio_ids:
            raise ValueError("rate prerequisite radios differ from qualification target")
        if any(not evidence.passed for evidence in self.prerequisites.radio_safety):
            raise ValueError("rate qualification requires passing per-radio safety evidence")
        for canary in self.prerequisites.native_ip_canaries:
            if (
                canary.sample_rate_hz != self.sample_rate_hz
                or canary.bandwidth_hz != self.bandwidth_hz
            ):
                raise ValueError("native-IP canary settings differ from qualification target")
            if not canary.passed:
                raise ValueError("rate qualification requires passing native-IP canaries")
        usb_control = self.prerequisites.usb_control_arm
        if (
            usb_control.sample_rate_hz != self.sample_rate_hz
            or usb_control.bandwidth_hz != self.bandwidth_hz
        ):
            raise ValueError("USB control-arm settings differ from qualification target")
        if not usb_control.passed:
            raise ValueError("rate qualification requires a passing USB control arm")
        if not self.prerequisites.writer_benchmark.passed:
            raise ValueError("rate qualification requires a passing 72 MB/s writer benchmark")
        return self


class ContiguousRateQualificationTargetV2(ContiguousRateQualificationTargetV1):
    """V2 target binding the independent USB control inventory and restoration evidence."""

    schema_version: Literal[2] = 2  # type: ignore[assignment]
    prerequisites: ContiguousRatePrerequisitesV2  # type: ignore[assignment]


class ContiguousRateQualificationTargetV3(ContiguousRateQualificationTargetV1):
    """V3 target qualified entirely on the exact production native-IP pair."""

    schema_version: Literal[3] = 3  # type: ignore[assignment]
    prerequisites: ContiguousRatePrerequisitesV3  # type: ignore[assignment]

    @model_validator(mode="after")
    def _identity_is_promotion_grade(self) -> Self:
        radio_ids = tuple(radio.radio_id for radio in self.expected_radios)
        if len(set(radio_ids)) != 2:
            raise ValueError("contiguous rate qualification requires two unique radios")
        if any(radio.firmware_version is None for radio in self.expected_radios):
            raise ValueError("rate qualification requires exact radio firmware identities")
        if self.expected_host.machine_id is None:
            raise ValueError("rate qualification requires an exact host machine identity")
        if self.expected_producer.source_revision is None:
            raise ValueError("rate qualification requires an exact producer source revision")
        if self.prerequisites.radio_ids != radio_ids:
            raise ValueError("rate prerequisite radios differ from qualification target")
        if any(not evidence.passed for evidence in self.prerequisites.radio_safety):
            raise ValueError("rate qualification requires passing per-radio safety evidence")
        for canary in self.prerequisites.native_ip_canaries:
            if (
                canary.sample_rate_hz != self.sample_rate_hz
                or canary.bandwidth_hz != self.bandwidth_hz
            ):
                raise ValueError("native-IP canary settings differ from qualification target")
            if not canary.passed:
                raise ValueError("rate qualification requires passing native-IP canaries")
        if not self.prerequisites.writer_benchmark.passed:
            raise ValueError("rate qualification requires a passing 72 MB/s writer benchmark")
        return self


class ContiguousRateQualificationTargetV4(ContiguousRateQualificationTargetV3):
    """V4 target for the exact production device-axis recording path."""

    schema_version: Literal[4] = 4  # type: ignore[assignment]
    prerequisites: ContiguousRatePrerequisitesV4  # type: ignore[assignment]

    @model_validator(mode="after")
    def _five_m_identity_matches_target(self) -> Self:
        evidence = self.prerequisites.five_m_characterization
        if evidence.radios != self.expected_radios:
            raise ValueError("5 MS/s radios differ from the V4 qualification target")
        if evidence.host != self.expected_host or evidence.producer != self.expected_producer:
            raise ValueError("5 MS/s runtime identity differs from the V4 qualification target")
        host_health = self.prerequisites.host_health
        if (
            host_health.before.host_name != self.expected_host.hostname
            or host_health.after.host_name != self.expected_host.hostname
        ):
            raise ValueError("host-health evidence host differs from the V4 qualification target")
        return self


class ContiguousRateQualificationTargetV5(ContiguousRateQualificationTargetV3):
    """V5 device-axis target binding scoped pre/post host-health evidence."""

    schema_version: Literal[5] = 5  # type: ignore[assignment]
    prerequisites: ContiguousRatePrerequisitesV5  # type: ignore[assignment]

    @model_validator(mode="after")
    def _five_m_identity_matches_target(self) -> Self:
        evidence = self.prerequisites.five_m_characterization
        if evidence.radios != self.expected_radios:
            raise ValueError("5 MS/s radios differ from the V5 qualification target")
        if evidence.host != self.expected_host or evidence.producer != self.expected_producer:
            raise ValueError("5 MS/s runtime identity differs from the V5 qualification target")
        host_health = self.prerequisites.host_health
        if (
            host_health.before.base.host_name != self.expected_host.hostname
            or host_health.after.base.host_name != self.expected_host.hostname
        ):
            raise ValueError("host-health evidence host differs from the V5 qualification target")
        return self


class ContiguousRateTrialEvidenceV1(ContractModel):
    """One verified recording manifest presented to the strict evaluator."""

    schema_version: Literal[1] = 1
    trial_id: QualificationId
    manifest_sha256: Sha256Digest
    digest_valid: bool
    manifest: RecordingManifestV2


class ContiguousRateTrialEvidenceV2(ContractModel):
    """One verified device-axis V3 bundle presented to the V4 evaluator."""

    schema_version: Literal[2] = 2
    trial_id: QualificationId
    manifest_sha256: Sha256Digest
    digest_valid: bool
    manifest: RecordingManifestV3


class ContiguousRateTrialCheckV1(ContractModel):
    schema_version: Literal[1] = 1
    trial_id: QualificationId
    session_id: str
    manifest_sha256: Sha256Digest
    passed: bool
    errors: tuple[str, ...]

    @model_validator(mode="after")
    def _decision_matches_errors(self) -> Self:
        if self.passed == bool(self.errors):
            raise ValueError("trial pass flag must be true exactly when no errors exist")
        return self


class ContiguousRateDeviceAxisStreamCheckV1(ContractModel):
    """Receipt-retained closure evidence for one device-axis stream."""

    schema_version: Literal[1] = 1
    radio_id: RadioId
    logical_sample_count: Annotated[int, Field(gt=0)]
    observed_sample_count: Annotated[int, Field(gt=0)]
    zero_fill_sample_count: Annotated[int, Field(ge=0)]
    continuity_segment_count: Annotated[int, Field(gt=0)]
    observed_iq_sha256: Sha256Digest
    logical_iq_sha256: Sha256Digest
    timeline_sha256: Sha256Digest
    gap_map_sha256: Sha256Digest
    validity_inventory_sha256: Sha256Digest


class ContiguousRateTrialCheckV2(ContiguousRateTrialCheckV1):
    """V4 trial decision retaining exact V3 stream evidence."""

    schema_version: Literal[2] = 2  # type: ignore[assignment]
    manifest_schema_version: Literal[3] = 3
    stream_checks: tuple[
        ContiguousRateDeviceAxisStreamCheckV1,
        ContiguousRateDeviceAxisStreamCheckV1,
    ]


class ContiguousRateQualificationReceiptV1(ContractModel):
    """Deterministic decision bound to the digests of every evaluated bundle."""

    kind: Literal["contiguous_rate_qualification"] = "contiguous_rate_qualification"
    schema_version: Literal[1] = 1
    target: ContiguousRateQualificationTargetV1
    target_digest: Sha256Digest
    created_utc_ns: Annotated[int, Field(ge=0)]
    complete: bool
    passed: bool
    checks: tuple[ContiguousRateTrialCheckV1, ...]

    @model_validator(mode="after")
    def _receipt_is_consistent(self) -> Self:
        expected_target_digest = contiguous_rate_qualification_target_digest(self.target)
        if self.target_digest != expected_target_digest:
            raise ValueError(
                "rate qualification target digest does not match target and prerequisites"
            )
        trial_ids = tuple(check.trial_id for check in self.checks)
        session_ids = tuple(check.session_id for check in self.checks)
        manifest_digests = tuple(check.manifest_sha256 for check in self.checks)
        if len(set(trial_ids)) != len(trial_ids):
            raise ValueError("rate qualification trial IDs must be unique")
        if len(set(session_ids)) != len(session_ids):
            raise ValueError("rate qualification session IDs must be unique")
        if len(set(manifest_digests)) != len(manifest_digests):
            raise ValueError("rate qualification manifest digests must be unique")
        required = self.target.policy.required_trial_count
        if len(self.checks) > required:
            raise ValueError("rate qualification has more checks than required trials")
        if self.complete != (len(self.checks) == required):
            raise ValueError("rate qualification complete flag disagrees with trial inventory")
        if self.passed != (self.complete and all(check.passed for check in self.checks)):
            raise ValueError("rate qualification pass flag disagrees with strict trial checks")
        return self


class ContiguousRateQualificationReceiptV2(ContiguousRateQualificationReceiptV1):
    """V2 decision binding the complete V2 target and its independent USB evidence."""

    schema_version: Literal[2] = 2  # type: ignore[assignment]
    target: ContiguousRateQualificationTargetV2


class ContiguousRateQualificationReceiptV3(ContiguousRateQualificationReceiptV1):
    """V3 decision bound only to production-native prerequisite evidence."""

    schema_version: Literal[3] = 3  # type: ignore[assignment]
    target: ContiguousRateQualificationTargetV3


class ContiguousRateQualificationReceiptV4(ContiguousRateQualificationReceiptV1):
    """V4 decision bound to exact device-axis V3 recorder evidence."""

    schema_version: Literal[4] = 4  # type: ignore[assignment]
    target: ContiguousRateQualificationTargetV4
    checks: tuple[ContiguousRateTrialCheckV2, ...]


class ContiguousRateQualificationReceiptV5(ContiguousRateQualificationReceiptV1):
    """V5 decision bound to V3 recorder and scoped host-health evidence."""

    schema_version: Literal[5] = 5  # type: ignore[assignment]
    target: ContiguousRateQualificationTargetV5
    checks: tuple[ContiguousRateTrialCheckV2, ...]


def contiguous_rate_qualification_target_digest(
    target: ContiguousRateQualificationTargetV1,
) -> str:
    """Bind the complete target, including every prerequisite evidence digest and metric."""

    return canonical_digest(target.model_dump(mode="json"))


@overload
def evaluate_contiguous_rate(
    target: ContiguousRateQualificationTargetV3,
    trials: tuple[ContiguousRateTrialEvidenceV1, ...],
    *,
    created_utc_ns: int,
) -> ContiguousRateQualificationReceiptV3: ...


@overload
def evaluate_contiguous_rate(
    target: ContiguousRateQualificationTargetV2,
    trials: tuple[ContiguousRateTrialEvidenceV1, ...],
    *,
    created_utc_ns: int,
) -> ContiguousRateQualificationReceiptV2: ...


@overload
def evaluate_contiguous_rate(
    target: ContiguousRateQualificationTargetV1,
    trials: tuple[ContiguousRateTrialEvidenceV1, ...],
    *,
    created_utc_ns: int,
) -> ContiguousRateQualificationReceiptV1: ...


def evaluate_contiguous_rate(
    target: ContiguousRateQualificationTargetV1,
    trials: tuple[ContiguousRateTrialEvidenceV1, ...],
    *,
    created_utc_ns: int,
) -> ContiguousRateQualificationReceiptV1:
    """Evaluate already-verified V2 manifests without touching hardware or storage."""

    if isinstance(
        target, (ContiguousRateQualificationTargetV4, ContiguousRateQualificationTargetV5)
    ):
        raise TypeError("V4/V5 targets require evaluate_device_axis_contiguous_rate")
    trial_ids = tuple(trial.trial_id for trial in trials)
    session_ids = tuple(trial.manifest.session_id for trial in trials)
    manifest_digests = tuple(trial.manifest_sha256 for trial in trials)
    if len(set(trial_ids)) != len(trial_ids):
        raise ValueError("rate qualification trial IDs must be unique")
    if len(set(session_ids)) != len(session_ids):
        raise ValueError("rate qualification session IDs must be unique")
    if len(set(manifest_digests)) != len(manifest_digests):
        raise ValueError("rate qualification manifest digests must be unique")
    if len(trials) > target.policy.required_trial_count:
        raise ValueError("rate qualification has more trials than the target requires")

    checks = tuple(_check_trial(target, trial) for trial in trials)
    complete = len(checks) == target.policy.required_trial_count
    receipt_type: type[ContiguousRateQualificationReceiptV1]
    if isinstance(target, ContiguousRateQualificationTargetV3):
        receipt_type = ContiguousRateQualificationReceiptV3
    elif isinstance(target, ContiguousRateQualificationTargetV2):
        receipt_type = ContiguousRateQualificationReceiptV2
    else:
        receipt_type = ContiguousRateQualificationReceiptV1
    return receipt_type(
        target=target,
        target_digest=contiguous_rate_qualification_target_digest(target),
        created_utc_ns=created_utc_ns,
        complete=complete,
        passed=complete and all(check.passed for check in checks),
        checks=checks,
    )


@overload
def evaluate_device_axis_contiguous_rate(
    target: ContiguousRateQualificationTargetV5,
    trials: tuple[ContiguousRateTrialEvidenceV2, ...],
    *,
    created_utc_ns: int,
) -> ContiguousRateQualificationReceiptV5: ...


@overload
def evaluate_device_axis_contiguous_rate(
    target: ContiguousRateQualificationTargetV4,
    trials: tuple[ContiguousRateTrialEvidenceV2, ...],
    *,
    created_utc_ns: int,
) -> ContiguousRateQualificationReceiptV4: ...


def evaluate_device_axis_contiguous_rate(
    target: ContiguousRateQualificationTargetV4 | ContiguousRateQualificationTargetV5,
    trials: tuple[ContiguousRateTrialEvidenceV2, ...],
    *,
    created_utc_ns: int,
) -> ContiguousRateQualificationReceiptV4 | ContiguousRateQualificationReceiptV5:
    """Evaluate verified V3 bundles for the exact production device-axis path."""

    trial_ids = tuple(trial.trial_id for trial in trials)
    session_ids = tuple(trial.manifest.session_id for trial in trials)
    manifest_digests = tuple(trial.manifest_sha256 for trial in trials)
    if len(set(trial_ids)) != len(trial_ids):
        raise ValueError("rate qualification trial IDs must be unique")
    if len(set(session_ids)) != len(session_ids):
        raise ValueError("rate qualification session IDs must be unique")
    if len(set(manifest_digests)) != len(manifest_digests):
        raise ValueError("rate qualification manifest digests must be unique")
    if len(trials) > target.policy.required_trial_count:
        raise ValueError("rate qualification has more trials than the target requires")

    checks = tuple(_check_device_axis_trial(target, trial) for trial in trials)
    complete = len(checks) == target.policy.required_trial_count
    if isinstance(target, ContiguousRateQualificationTargetV5):
        return ContiguousRateQualificationReceiptV5(
            target=target,
            target_digest=contiguous_rate_qualification_target_digest(target),
            created_utc_ns=created_utc_ns,
            complete=complete,
            passed=complete and all(check.passed for check in checks),
            checks=checks,
        )
    return ContiguousRateQualificationReceiptV4(
        target=target,
        target_digest=contiguous_rate_qualification_target_digest(target),
        created_utc_ns=created_utc_ns,
        complete=complete,
        passed=complete and all(check.passed for check in checks),
        checks=checks,
    )


def _check_device_axis_trial(
    target: ContiguousRateQualificationTargetV4 | ContiguousRateQualificationTargetV5,
    trial: ContiguousRateTrialEvidenceV2,
) -> ContiguousRateTrialCheckV2:
    manifest = trial.manifest
    policy = target.policy
    errors: list[str] = []

    if not trial.digest_valid:
        errors.append("bundle digest verification failed")
    if manifest.state is not CaptureState.COMMITTED:
        errors.append(f"capture state is {manifest.state.value}, not committed")
    if manifest.capture_plan.profile_revision.revision_digest != target.profile_revision_digest:
        errors.append("profile revision digest differs from qualification target")
    if manifest.capture_plan.plan_digest != target.capture_plan_digest:
        errors.append("capture plan digest differs from qualification target")
    if manifest.capture_plan.profile_revision.profile.storage_policy != (
        DEVICE_AXIS_STORAGE_POLICY_V1
    ):
        errors.append("capture did not use the device-axis storage policy")
    if manifest.compression.policy_id != DEVICE_AXIS_STORAGE_POLICY_V1:
        errors.append("manifest compression policy is not device-axis storage")
    if manifest.host != target.expected_host:
        errors.append("capture host identity differs from qualification target")
    if manifest.producer != target.expected_producer:
        errors.append("capture producer identity differs from qualification target")
    missing_tags = sorted(set(policy.required_tags).difference(manifest.tags))
    if missing_tags:
        errors.append(f"capture lacks required tags: {', '.join(missing_tags)}")

    expected_radios = {radio.radio_id: radio for radio in target.expected_radios}
    actual_radios = {stream.radio.radio_id: stream.radio for stream in manifest.streams}
    if actual_radios != expected_radios:
        errors.append("stream radio identities differ from qualification target")

    overlap = manifest.synchronization.overlap_fraction
    if manifest.synchronization.grade is not SynchronizationGrade.BEST_EFFORT_OBSERVED:
        errors.append("two-radio synchronization is not best-effort observed")
    if overlap is None or overlap < policy.minimum_overlap_fraction:
        errors.append("two-radio overlap is below the qualification threshold")

    stream_checks: list[ContiguousRateDeviceAxisStreamCheckV1] = []
    for stream in manifest.streams:
        prefix = f"{stream.radio.radio_id}: "
        applied = stream.applied_settings
        continuity = stream.continuity
        stream_checks.append(
            ContiguousRateDeviceAxisStreamCheckV1(
                radio_id=stream.radio.radio_id,
                logical_sample_count=stream.logical_sample_count,
                observed_sample_count=stream.observed_sample_count,
                zero_fill_sample_count=stream.zero_fill_sample_count,
                continuity_segment_count=continuity.segment_count,
                observed_iq_sha256=stream.observed_iq_sha256,
                logical_iq_sha256=stream.logical_iq_sha256,
                timeline_sha256=stream.timeline_sha256,
                gap_map_sha256=stream.gap_map_sha256,
                validity_inventory_sha256=stream.validity_inventory_sha256,
            )
        )
        if stream.state is not StreamState.COMPLETE:
            errors.append(prefix + f"stream state is {stream.state.value}, not complete")
        if stream.requested_settings.sample_rate_hz != target.sample_rate_hz:
            errors.append(prefix + "requested sample rate differs from qualification target")
        if stream.requested_settings.bandwidth_hz != target.bandwidth_hz:
            errors.append(prefix + "requested bandwidth differs from qualification target")
        if applied.sample_rate_hz != target.sample_rate_hz:
            errors.append(prefix + "applied sample rate differs from qualification target")
        if applied.bandwidth_hz != target.bandwidth_hz:
            errors.append(prefix + "applied bandwidth differs from qualification target")
        if stream.requested_sample_count != target.requested_sample_count:
            errors.append(prefix + "requested sample count differs from qualification target")
        if not (
            stream.logical_sample_count
            == stream.observed_sample_count
            == continuity.observed_sample_count
            == continuity.device_span_sample_count
            == target.requested_sample_count
        ):
            errors.append(prefix + "observed samples do not close the requested device span")
        if stream.zero_fill_sample_count:
            errors.append(prefix + "device-axis zero-fill sample count is nonzero")
        if stream.observed_iq_sha256 != stream.logical_iq_sha256:
            errors.append(prefix + "logical IQ digest differs from observed IQ digest")
        if any(
            chunk.content_kind is not DeviceAxisContentKind.OBSERVED
            or chunk.continuity_segment_index != 0
            for chunk in stream.chunks
        ):
            errors.append(prefix + "device-axis chunks are not one all-observed segment")
        if continuity.segment_count != 1:
            errors.append(prefix + "continuity segment count is not exactly one")
        if not continuity.sample_loss_observable:
            errors.append(prefix + "sample loss is not counter-observable")
        if continuity.kernel_buffers != policy.required_kernel_buffers:
            errors.append(prefix + "kernel-buffer readback differs from qualification policy")
        if continuity.metadata_abi_version != policy.required_metadata_abi_version:
            errors.append(prefix + "metadata ABI differs from qualification policy")
        if continuity.queue_capacity_refills != policy.required_queue_capacity_refills:
            errors.append(prefix + "queue capacity differs from qualification policy")
        if (
            continuity.queue_high_water_refills / continuity.queue_capacity_refills
            > policy.maximum_queue_high_water_fraction
        ):
            errors.append(prefix + "queue high-water exceeds qualification policy")
        if continuity.total_observed_gap_count:
            errors.append(prefix + "counter gap count is nonzero")
        if continuity.total_observed_missing_sample_count:
            errors.append(prefix + "counter-proven missing sample count is nonzero")
        if continuity.total_observed_overflow_count:
            errors.append(prefix + "overflow count is nonzero")
        if continuity.enqueue_failure_count:
            errors.append(prefix + "receive-queue enqueue failure count is nonzero")
        if (
            policy.maximum_refill_service_interval_ns is not None
            and continuity.maximum_refill_service_interval_ns
            > policy.maximum_refill_service_interval_ns
        ):
            errors.append(prefix + "maximum refill service interval exceeds qualification policy")

    if len(stream_checks) != 2:
        raise ValueError("device-axis qualification requires exactly two stream checks")
    return ContiguousRateTrialCheckV2(
        trial_id=trial.trial_id,
        session_id=manifest.session_id,
        manifest_sha256=trial.manifest_sha256,
        stream_checks=(stream_checks[0], stream_checks[1]),
        passed=not errors,
        errors=tuple(errors),
    )


def _check_trial(
    target: ContiguousRateQualificationTargetV1,
    trial: ContiguousRateTrialEvidenceV1,
) -> ContiguousRateTrialCheckV1:
    manifest = trial.manifest
    policy = target.policy
    errors: list[str] = []

    if not trial.digest_valid:
        errors.append("bundle digest verification failed")
    if manifest.state is not CaptureState.COMMITTED:
        errors.append(f"capture state is {manifest.state.value}, not committed")
    if manifest.capture_plan.profile_revision.revision_digest != target.profile_revision_digest:
        errors.append("profile revision digest differs from qualification target")
    if manifest.capture_plan.plan_digest != target.capture_plan_digest:
        errors.append("capture plan digest differs from qualification target")
    if manifest.host != target.expected_host:
        errors.append("capture host identity differs from qualification target")
    if manifest.producer != target.expected_producer:
        errors.append("capture producer identity differs from qualification target")
    missing_tags = sorted(set(policy.required_tags).difference(manifest.tags))
    if missing_tags:
        errors.append(f"capture lacks required tags: {', '.join(missing_tags)}")

    expected_radios = {radio.radio_id: radio for radio in target.expected_radios}
    actual_radios = {stream.radio.radio_id: stream.radio for stream in manifest.streams}
    if actual_radios != expected_radios:
        errors.append("stream radio identities differ from qualification target")

    overlap = manifest.synchronization.overlap_fraction
    if manifest.synchronization.grade is not SynchronizationGrade.BEST_EFFORT_OBSERVED:
        errors.append("two-radio synchronization is not best-effort observed")
    if overlap is None or overlap < policy.minimum_overlap_fraction:
        errors.append("two-radio overlap is below the qualification threshold")

    for stream in manifest.streams:
        prefix = f"{stream.radio.radio_id}: "
        applied = stream.applied_settings
        continuity = stream.continuity
        if stream.state is not StreamState.COMPLETE:
            errors.append(prefix + f"stream state is {stream.state.value}, not complete")
        if stream.requested_settings.sample_rate_hz != target.sample_rate_hz:
            errors.append(prefix + "requested sample rate differs from qualification target")
        if stream.requested_settings.bandwidth_hz != target.bandwidth_hz:
            errors.append(prefix + "requested bandwidth differs from qualification target")
        if applied is None or applied.sample_rate_hz != target.sample_rate_hz:
            errors.append(prefix + "applied sample rate differs from qualification target")
        if applied is None or applied.bandwidth_hz != target.bandwidth_hz:
            errors.append(prefix + "applied bandwidth differs from qualification target")
        if stream.requested_sample_count != target.requested_sample_count:
            errors.append(prefix + "requested sample count differs from qualification target")
        if not (
            stream.captured_sample_count
            == continuity.observed_sample_count
            == continuity.device_span_sample_count
            == target.requested_sample_count
        ):
            errors.append(prefix + "observed samples do not close the requested device span")
        if not continuity.sample_loss_observable:
            errors.append(prefix + "sample loss is not counter-observable")
        if continuity.kernel_buffers != policy.required_kernel_buffers:
            errors.append(prefix + "kernel-buffer readback differs from qualification policy")
        if continuity.metadata_abi_version != policy.required_metadata_abi_version:
            errors.append(prefix + "metadata ABI differs from qualification policy")
        if continuity.queue_capacity_refills != policy.required_queue_capacity_refills:
            errors.append(prefix + "queue capacity differs from qualification policy")
        if (
            continuity.queue_high_water_refills / continuity.queue_capacity_refills
            > policy.maximum_queue_high_water_fraction
        ):
            errors.append(prefix + "queue high-water exceeds qualification policy")
        if continuity.total_observed_gap_count:
            errors.append(prefix + "counter gap count is nonzero")
        if continuity.total_observed_missing_sample_count:
            errors.append(prefix + "counter-proven missing sample count is nonzero")
        if continuity.total_observed_overflow_count:
            errors.append(prefix + "overflow count is nonzero")
        if continuity.enqueue_failure_count:
            errors.append(prefix + "receive-queue enqueue failure count is nonzero")
        if (
            policy.maximum_refill_service_interval_ns is not None
            and continuity.maximum_refill_service_interval_ns
            > policy.maximum_refill_service_interval_ns
        ):
            errors.append(prefix + "maximum refill service interval exceeds qualification policy")

    return ContiguousRateTrialCheckV1(
        trial_id=trial.trial_id,
        session_id=manifest.session_id,
        manifest_sha256=trial.manifest_sha256,
        passed=not errors,
        errors=tuple(errors),
    )
