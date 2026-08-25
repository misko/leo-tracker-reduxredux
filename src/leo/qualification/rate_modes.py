"""Strict, bundle-bound qualification for contiguous capture rates."""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import Field, StringConstraints, field_validator, model_validator

from leo.contracts.base import ContractModel
from leo.contracts.digests import Sha256Digest, canonical_digest
from leo.contracts.radio import RadioId, RadioIdentityV1
from leo.contracts.recording import (
    HostIdentityV1,
    ProducerV1,
    RecordingManifestV2,
)
from leo.contracts.states import CaptureState, StreamState, SynchronizationGrade

QualificationId = Annotated[
    str,
    StringConstraints(min_length=1, max_length=96, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$"),
]
_ONE_SECOND_NS = 1_000_000_000
_MINIMUM_WRITER_BYTES_PER_SECOND = 72_000_000


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


class ContiguousRateTrialEvidenceV1(ContractModel):
    """One verified recording manifest presented to the strict evaluator."""

    schema_version: Literal[1] = 1
    trial_id: QualificationId
    manifest_sha256: Sha256Digest
    digest_valid: bool
    manifest: RecordingManifestV2


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


def contiguous_rate_qualification_target_digest(
    target: ContiguousRateQualificationTargetV1,
) -> str:
    """Bind the complete target, including every prerequisite evidence digest and metric."""

    return canonical_digest(target.model_dump(mode="json"))


def evaluate_contiguous_rate(
    target: ContiguousRateQualificationTargetV1,
    trials: tuple[ContiguousRateTrialEvidenceV1, ...],
    *,
    created_utc_ns: int,
) -> ContiguousRateQualificationReceiptV1:
    """Evaluate already-verified V2 manifests without touching hardware or storage."""

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
    return ContiguousRateQualificationReceiptV1(
        target=target,
        target_digest=contiguous_rate_qualification_target_digest(target),
        created_utc_ns=created_utc_ns,
        complete=complete,
        passed=complete and all(check.passed for check in checks),
        checks=checks,
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
