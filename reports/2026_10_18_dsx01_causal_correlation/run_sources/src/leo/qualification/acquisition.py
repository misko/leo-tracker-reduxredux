"""Repeatable acquisition qualification and generated-IQ writer benchmarks."""

from __future__ import annotations

import math
import os
import platform
import socket
import time
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path
from threading import Event
from typing import Annotated, Literal, Self
from uuid import uuid4

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from leo.acquisition import AcquisitionApplication, CaptureSessionResult
from leo.contracts.profile import CapturePlanV1, CaptureProfileRevisionV1, CaptureProfileV1
from leo.contracts.radio import (
    IqBlockMetadataV1,
    NanosecondIntervalV1,
    RadioIdentityV1,
    RadioSettingsV1,
    ReceiverGainV1,
)
from leo.contracts.recording import (
    CompressionSettingsV1,
    HostIdentityV1,
    ProducerV1,
    RecordingManifestV1,
    RecordingStreamV1,
    StreamTimingV1,
    SynchronizationSummaryV1,
    TimingEstimateV1,
)
from leo.contracts.states import (
    CaptureState,
    ContinuityStatus,
    GainMode,
    RadioTransport,
    SourceType,
    StreamState,
    SynchronizationGrade,
    SynchronizationMode,
    TimingMethod,
)
from leo.domain.iq import IqBlock
from leo.domain.profiles import compile_capture_plan
from leo.radio import RadioSource
from leo.storage import BundleNotFoundError, PublishedBundle, RecordingStore
from leo.storage.writer import StreamWriteReceipt

QualificationId = Annotated[
    str,
    StringConstraints(min_length=1, max_length=96, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$"),
]
SourceFactory = Callable[[str], RadioSource]
MonotonicNs = Callable[[], int]
UtcNs = Callable[[], int]


class QualificationModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class AcquisitionAcceptancePolicyV1(QualificationModel):
    schema_version: Literal[1] = 1
    minimum_successful_trial_fraction: Annotated[float, Field(ge=0, le=1)] = 0.95
    minimum_estimated_overlap_fraction: Annotated[float, Field(ge=0, le=1)] = 0.99
    minimum_overlap_passing_trial_fraction: Annotated[float, Field(ge=0, le=1)] = 0.95
    maximum_false_complete_count: Annotated[int, Field(ge=0)] = 0
    maximum_false_coherent_count: Annotated[int, Field(ge=0)] = 0
    require_all_digests_valid: bool = True


class QualificationTrialV1(QualificationModel):
    schema_version: Literal[1] = 1
    trial_id: str
    session_id: str
    state: CaptureState
    bundle_uri: str | None = None
    manifest_sha256: str | None = None
    digest_valid: bool | None = None
    verification_error: str | None = None
    elapsed_seconds: Annotated[float | None, Field(gt=0)] = None
    acquisition_throughput_mb_s: Annotated[float | None, Field(ge=0)] = None
    uncompressed_bytes: Annotated[int, Field(ge=0)] = 0
    compressed_bytes: Annotated[int, Field(ge=0)] = 0
    compression_ratio: Annotated[float | None, Field(gt=0)] = None
    gap_count: Annotated[int, Field(ge=0)] = 0
    overflow_count: Annotated[int, Field(ge=0)] = 0
    estimated_start_skew_ns: Annotated[int | None, Field(ge=0)] = None
    start_skew_uncertainty_ns: Annotated[int | None, Field(ge=0)] = None
    estimated_overlap_ns: Annotated[int | None, Field(ge=0)] = None
    guaranteed_overlap_ns: Annotated[int | None, Field(ge=0)] = None
    overlap_fraction: Annotated[float | None, Field(ge=0, le=1)] = None
    false_complete_count: Annotated[int, Field(ge=0)] = 0
    false_coherent_count: Annotated[int, Field(ge=0)] = 0
    errors: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _bundle_evidence_is_consistent(self) -> Self:
        present = (self.bundle_uri is not None, self.manifest_sha256 is not None)
        if present[0] != present[1]:
            raise ValueError("bundle URI and manifest digest must appear together")
        if self.digest_valid is not None and self.bundle_uri is None:
            raise ValueError("digest result requires a published bundle")
        if self.verification_error is not None and self.digest_valid is not False:
            raise ValueError("verification error requires an invalid digest result")
        return self


class AcquisitionAggregateV1(QualificationModel):
    schema_version: Literal[1] = 1
    requested_trial_count: Annotated[int, Field(gt=0)]
    completed_trial_count: Annotated[int, Field(ge=0)]
    committed_count: Annotated[int, Field(ge=0)]
    degraded_count: Annotated[int, Field(ge=0)]
    failed_count: Annotated[int, Field(ge=0)]
    successful_count: Annotated[int, Field(ge=0)]
    successful_trial_fraction: Annotated[float, Field(ge=0, le=1)]
    overlap_passing_count: Annotated[int, Field(ge=0)]
    overlap_passing_trial_fraction: Annotated[float, Field(ge=0, le=1)]
    digest_valid_count: Annotated[int, Field(ge=0)]
    digest_invalid_count: Annotated[int, Field(ge=0)]
    all_digests_valid: bool
    total_gap_count: Annotated[int, Field(ge=0)]
    total_overflow_count: Annotated[int, Field(ge=0)]
    false_complete_count: Annotated[int, Field(ge=0)]
    false_coherent_count: Annotated[int, Field(ge=0)]
    mean_estimated_start_skew_ns: float | None = None
    maximum_estimated_start_skew_ns: int | None = None
    mean_start_skew_uncertainty_ns: float | None = None
    maximum_start_skew_uncertainty_ns: int | None = None
    mean_estimated_overlap_ns: float | None = None
    mean_guaranteed_overlap_ns: float | None = None
    mean_overlap_fraction: float | None = None
    minimum_overlap_fraction: float | None = None
    total_uncompressed_bytes: Annotated[int, Field(ge=0)]
    total_compressed_bytes: Annotated[int, Field(ge=0)]
    compression_ratio: Annotated[float | None, Field(gt=0)] = None
    mean_acquisition_throughput_mb_s: Annotated[float | None, Field(ge=0)] = None
    minimum_acquisition_throughput_mb_s: Annotated[float | None, Field(ge=0)] = None


class AcquisitionQualificationReceiptV1(QualificationModel):
    kind: Literal["acquisition_qualification"] = "acquisition_qualification"
    schema_version: Literal[1] = 1
    qualification_id: QualificationId
    profile_name: str
    profile_revision_digest: str
    capture_plan_digest: str
    radio_ids: tuple[str, ...]
    requested_trial_count: Annotated[int, Field(gt=0)]
    policy: AcquisitionAcceptancePolicyV1
    created_utc_ns: Annotated[int, Field(ge=0)]
    updated_utc_ns: Annotated[int, Field(ge=0)]
    cancelled: bool
    complete: bool
    passed: bool
    recordings_preserved: Literal[True] = True
    trials: tuple[QualificationTrialV1, ...]
    aggregate: AcquisitionAggregateV1

    @model_validator(mode="after")
    def _receipt_is_consistent(self) -> Self:
        if self.updated_utc_ns < self.created_utc_ns:
            raise ValueError("qualification receipt update precedes creation")
        if not 1 <= len(self.radio_ids) <= 2 or len(set(self.radio_ids)) != len(self.radio_ids):
            raise ValueError("qualification requires one or two unique radios")
        trial_ids = tuple(trial.trial_id for trial in self.trials)
        session_ids = tuple(trial.session_id for trial in self.trials)
        if len(set(trial_ids)) != len(trial_ids) or len(set(session_ids)) != len(session_ids):
            raise ValueError("qualification trial and session IDs must be unique")
        if len(self.trials) > self.requested_trial_count:
            raise ValueError("qualification has more trials than requested")
        if self.aggregate.completed_trial_count != len(self.trials):
            raise ValueError("aggregate completed count disagrees with trial inventory")
        if self.complete != (len(self.trials) == self.requested_trial_count):
            raise ValueError("qualification complete flag disagrees with trial inventory")
        if self.passed and (not self.complete or self.cancelled):
            raise ValueError("incomplete or cancelled qualification cannot pass")
        return self


class WriterBenchmarkConfigV1(QualificationModel):
    schema_version: Literal[1] = 1
    duration_seconds: Annotated[float, Field(gt=0, le=3600)] = 1.0
    minimum_throughput_mb_s: Annotated[float, Field(gt=0)] = 60.0
    block_uncompressed_bytes: Annotated[int, Field(ge=16_384, le=128 * 1024 * 1024)] = (
        128 * 1024 * 1024
    )
    receiver_count: Literal[1, 2] = 2
    zstd_level: Annotated[int, Field(ge=-10, le=22)] = 3
    random_seed: Annotated[int, Field(ge=0)] = 20260819

    @model_validator(mode="after")
    def _block_has_whole_samples(self) -> Self:
        bytes_per_sample = self.receiver_count * 4
        if self.block_uncompressed_bytes % bytes_per_sample:
            raise ValueError("benchmark block bytes must contain whole CI16 sample frames")
        return self


class WriterBenchmarkReceiptV1(QualificationModel):
    kind: Literal["writer_benchmark"] = "writer_benchmark"
    schema_version: Literal[1] = 1
    benchmark_id: QualificationId
    configuration: WriterBenchmarkConfigV1
    created_utc_ns: Annotated[int, Field(ge=0)]
    finalized_utc_ns: Annotated[int, Field(ge=0)]
    cancelled: bool
    passed: bool
    bundle_uri: str | None = None
    manifest_sha256: str | None = None
    digest_valid: bool | None = None
    elapsed_seconds: Annotated[float, Field(ge=0)]
    block_count: Annotated[int, Field(ge=0)]
    uncompressed_bytes: Annotated[int, Field(ge=0)]
    compressed_bytes: Annotated[int, Field(ge=0)]
    compression_ratio: Annotated[float | None, Field(gt=0)] = None
    throughput_mb_s: Annotated[float, Field(ge=0)]
    recordings_preserved: Literal[True] = True
    error: str | None = None

    @model_validator(mode="after")
    def _result_is_consistent(self) -> Self:
        if self.finalized_utc_ns < self.created_utc_ns:
            raise ValueError("writer benchmark finalization precedes creation")
        present = (self.bundle_uri is not None, self.manifest_sha256 is not None)
        if present[0] != present[1]:
            raise ValueError("benchmark bundle URI and manifest digest must appear together")
        if self.digest_valid is not None and self.bundle_uri is None:
            raise ValueError("benchmark digest result requires a bundle")
        if self.passed and (self.cancelled or self.digest_valid is not True):
            raise ValueError("cancelled or unverified benchmark cannot pass")
        return self


class AcquisitionQualificationHarness:
    def __init__(
        self,
        store: RecordingStore,
        application: AcquisitionApplication,
        *,
        monotonic_ns: MonotonicNs = time.monotonic_ns,
        utc_ns: UtcNs = time.time_ns,
    ) -> None:
        _reject_qnap_path(store.root)
        self.store = store
        self.application = application
        self._monotonic_ns = monotonic_ns
        self._utc_ns = utc_ns

    def run(
        self,
        plan: CapturePlanV1,
        source_factory: SourceFactory,
        *,
        qualification_id: QualificationId,
        trial_count: int,
        receipt_path: Path,
        cancel: Event | None = None,
        policy: AcquisitionAcceptancePolicyV1 | None = None,
        resume: bool = True,
    ) -> AcquisitionQualificationReceiptV1:
        if trial_count <= 0:
            raise ValueError("qualification trial count must be positive")
        _reject_qnap_path(receipt_path)
        event = cancel or Event()
        acceptance = policy or AcquisitionAcceptancePolicyV1()
        existing = self._load_existing(
            receipt_path,
            plan,
            qualification_id,
            trial_count,
            acceptance,
            resume,
        )
        created_utc_ns = self._utc_ns() if existing is None else existing.created_utc_ns
        trials = [] if existing is None else list(existing.trials)
        completed = {trial.trial_id for trial in trials}
        receipt = _qualification_receipt(
            plan,
            qualification_id,
            trial_count,
            acceptance,
            created_utc_ns,
            self._utc_ns(),
            event.is_set(),
            tuple(trials),
        )
        _atomic_write_model(receipt_path, receipt)

        for index in range(trial_count):
            trial_id = _trial_id(qualification_id, index)
            if trial_id in completed:
                continue
            if event.is_set():
                break
            session_id = trial_id
            recovered = self._recover_trial(trial_id, session_id)
            if recovered is not None:
                trial = recovered
            else:
                started_ns = self._monotonic_ns()
                sources = {radio_id: source_factory(radio_id) for radio_id in plan.radio_ids}
                result = self.application.once(
                    plan,
                    sources,
                    session_id=session_id,
                    cancel=event,
                    extra_tags=("QUALIFICATION",),
                )
                ended_ns = self._monotonic_ns()
                elapsed = max(1, ended_ns - started_ns) / 1_000_000_000
                trial = self._trial_from_result(trial_id, result, elapsed)
            trials.append(trial)
            completed.add(trial_id)
            receipt = _qualification_receipt(
                plan,
                qualification_id,
                trial_count,
                acceptance,
                created_utc_ns,
                self._utc_ns(),
                event.is_set(),
                tuple(trials),
            )
            _atomic_write_model(receipt_path, receipt)
            if event.is_set():
                break
        return receipt

    def _load_existing(
        self,
        path: Path,
        plan: CapturePlanV1,
        qualification_id: str,
        trial_count: int,
        policy: AcquisitionAcceptancePolicyV1,
        resume: bool,
    ) -> AcquisitionQualificationReceiptV1 | None:
        if not path.exists():
            return None
        if not resume:
            raise FileExistsError(f"qualification receipt already exists: {path}")
        receipt = AcquisitionQualificationReceiptV1.model_validate_json(path.read_bytes())
        expected = (
            qualification_id,
            plan.profile_revision.revision_digest,
            plan.plan_digest,
            plan.radio_ids,
            trial_count,
            policy,
        )
        observed = (
            receipt.qualification_id,
            receipt.profile_revision_digest,
            receipt.capture_plan_digest,
            receipt.radio_ids,
            receipt.requested_trial_count,
            receipt.policy,
        )
        if observed != expected:
            raise ValueError("existing qualification receipt does not match this request")
        return receipt

    def _recover_trial(
        self,
        trial_id: str,
        session_id: str,
    ) -> QualificationTrialV1 | None:
        try:
            bundle = self.store.inspect(session_id)
        except BundleNotFoundError:
            spool = self.store.spool_root / f"{session_id}.partial"
            if not spool.exists():
                return None
            return QualificationTrialV1(
                trial_id=trial_id,
                session_id=session_id,
                state=CaptureState.FAILED,
                errors=("incomplete spool from an interrupted qualification trial",),
            )
        except Exception as error:
            return QualificationTrialV1(
                trial_id=trial_id,
                session_id=session_id,
                state=CaptureState.FAILED,
                errors=(f"committed bundle inspection failed: {type(error).__name__}: {error}",),
            )
        return self._trial_from_bundle(trial_id, bundle, elapsed_seconds=None)

    def _trial_from_result(
        self,
        trial_id: str,
        result: CaptureSessionResult,
        elapsed_seconds: float,
    ) -> QualificationTrialV1:
        if result.bundle is None:
            return QualificationTrialV1(
                trial_id=trial_id,
                session_id=result.session_id,
                state=result.state,
                elapsed_seconds=elapsed_seconds,
                errors=result.errors,
            )
        return self._trial_from_bundle(
            trial_id,
            result.bundle,
            elapsed_seconds=elapsed_seconds,
            errors=result.errors,
        )

    def _trial_from_bundle(
        self,
        trial_id: str,
        bundle: PublishedBundle,
        *,
        elapsed_seconds: float | None,
        errors: tuple[str, ...] = (),
    ) -> QualificationTrialV1:
        manifest = bundle.manifest
        verification_error = None
        try:
            report = self.store.verify(bundle)
            digest_valid = True
            uncompressed_bytes = report.uncompressed_bytes
            compressed_bytes = report.compressed_bytes
        except Exception as error:
            digest_valid = False
            verification_error = f"{type(error).__name__}: {error}"
            uncompressed_bytes = sum(
                chunk.uncompressed_bytes for stream in manifest.streams for chunk in stream.chunks
            )
            compressed_bytes = sum(
                chunk.compressed_bytes for stream in manifest.streams for chunk in stream.chunks
            )
        sync = manifest.synchronization
        stream_claim_is_false = any(
            stream.state is StreamState.COMPLETE
            and (
                not digest_valid
                or stream.captured_sample_count != stream.requested_sample_count
                or stream.timing is None
            )
            for stream in manifest.streams
        )
        capture_claim_is_false = manifest.state is CaptureState.COMMITTED and any(
            stream.state is not StreamState.COMPLETE for stream in manifest.streams
        )
        false_complete = int(stream_claim_is_false or capture_claim_is_false)
        false_coherent = int(bool(sync.phase_coherent))
        compression_ratio = uncompressed_bytes / compressed_bytes if compressed_bytes else None
        throughput = (
            uncompressed_bytes / 1_000_000 / elapsed_seconds
            if elapsed_seconds is not None
            else None
        )
        return QualificationTrialV1(
            trial_id=trial_id,
            session_id=manifest.session_id,
            state=manifest.state,
            bundle_uri=bundle.uri,
            manifest_sha256=bundle.manifest_sha256,
            digest_valid=digest_valid,
            verification_error=verification_error,
            elapsed_seconds=elapsed_seconds,
            acquisition_throughput_mb_s=throughput,
            uncompressed_bytes=uncompressed_bytes,
            compressed_bytes=compressed_bytes,
            compression_ratio=compression_ratio,
            gap_count=sum(stream.continuity.gap_count for stream in manifest.streams),
            overflow_count=sum(stream.continuity.overflow_count for stream in manifest.streams),
            estimated_start_skew_ns=sync.estimated_start_skew_ns,
            start_skew_uncertainty_ns=sync.start_skew_uncertainty_ns,
            estimated_overlap_ns=sync.estimated_overlap_ns,
            guaranteed_overlap_ns=sync.guaranteed_overlap_ns,
            overlap_fraction=sync.overlap_fraction,
            false_complete_count=false_complete,
            false_coherent_count=false_coherent,
            errors=errors,
        )


class WriterThroughputBenchmark:
    def __init__(
        self,
        store: RecordingStore,
        *,
        monotonic_ns: MonotonicNs = time.monotonic_ns,
        utc_ns: UtcNs = time.time_ns,
    ) -> None:
        _reject_qnap_path(store.root)
        self.store = store
        self._monotonic_ns = monotonic_ns
        self._utc_ns = utc_ns

    def run(
        self,
        *,
        benchmark_id: QualificationId,
        receipt_path: Path,
        configuration: WriterBenchmarkConfigV1 | None = None,
        cancel: Event | None = None,
        resume: bool = True,
    ) -> WriterBenchmarkReceiptV1:
        config = configuration or WriterBenchmarkConfigV1()
        _reject_qnap_path(receipt_path)
        event = cancel or Event()
        if receipt_path.exists():
            if not resume:
                raise FileExistsError(f"writer benchmark receipt already exists: {receipt_path}")
            existing = WriterBenchmarkReceiptV1.model_validate_json(receipt_path.read_bytes())
            if existing.benchmark_id != benchmark_id or existing.configuration != config:
                raise ValueError("existing writer benchmark receipt does not match this request")
            return existing
        try:
            self.store.inspect(benchmark_id)
        except BundleNotFoundError:
            if (self.store.spool_root / f"{benchmark_id}.partial").exists():
                raise FileExistsError(
                    "writer benchmark has an incomplete spool but no receipt; refusing to overwrite"
                ) from None
        else:
            raise FileExistsError(
                "writer benchmark bundle exists without its receipt; refusing to duplicate it"
            )
        created_utc_ns = self._utc_ns()
        if event.is_set():
            receipt = WriterBenchmarkReceiptV1(
                benchmark_id=benchmark_id,
                configuration=config,
                created_utc_ns=created_utc_ns,
                finalized_utc_ns=max(created_utc_ns, self._utc_ns()),
                cancelled=True,
                passed=False,
                elapsed_seconds=0,
                block_count=0,
                uncompressed_bytes=0,
                compressed_bytes=0,
                throughput_mb_s=0,
                error="cancelled before writer benchmark started",
            )
            _atomic_write_model(receipt_path, receipt)
            return receipt

        compression = CompressionSettingsV1(
            policy_id="writer-benchmark-zstd-v1",
            level=config.zstd_level,
            target_uncompressed_bytes=config.block_uncompressed_bytes,
        )
        writer = self.store.begin(benchmark_id, compression)
        identity = RadioIdentityV1(
            radio_id="writer-benchmark",
            serial="generated-writer-benchmark",
            uri="generated://writer-benchmark",
            transport=RadioTransport.FAKE,
            model="Generated CI16",
        )
        receiver_ids = tuple(range(config.receiver_count))
        stream_writer = writer.open_stream("stream-0", identity, receiver_ids)
        sample_count = config.block_uncompressed_bytes // (config.receiver_count * 4)
        samples = _generated_ci16(sample_count, config.receiver_count, config.random_seed)
        started_monotonic_ns = self._monotonic_ns()
        deadline_ns = started_monotonic_ns + round(config.duration_seconds * 1_000_000_000)
        block_count = 0
        captured_samples = 0
        first_utc_ns = self._utc_ns()
        while block_count == 0 or self._monotonic_ns() < deadline_ns:
            if event.is_set():
                break
            observed_utc_ns = self._utc_ns()
            observed_monotonic_ns = self._monotonic_ns()
            metadata = IqBlockMetadataV1(
                radio_id=identity.radio_id,
                receiver_ids=receiver_ids,
                sample_count=sample_count,
                session_sample_start=captured_samples,
                host_request_utc_ns=NanosecondIntervalV1(
                    lower_ns=observed_utc_ns,
                    upper_ns=observed_utc_ns,
                ),
                host_request_monotonic_ns=NanosecondIntervalV1(
                    lower_ns=observed_monotonic_ns,
                    upper_ns=observed_monotonic_ns,
                ),
                timing_method=TimingMethod.HOST_BRACKET,
                source_sequence=block_count,
                continuity=(
                    ContinuityStatus.UNKNOWN if block_count == 0 else ContinuityStatus.CONTIGUOUS
                ),
                hardware_metadata={"generated": True, "seed": config.random_seed},
            )
            stream_writer.append(IqBlock(samples=samples, metadata=metadata))
            block_count += 1
            captured_samples += sample_count
        stream_receipt = stream_writer.finalize()
        finished_monotonic_ns = self._monotonic_ns()
        finalized_utc_ns = max(first_utc_ns, self._utc_ns())
        elapsed_seconds = max(1, finished_monotonic_ns - started_monotonic_ns) / 1e9
        published = writer.publish(
            _benchmark_manifest(
                benchmark_id,
                identity,
                receiver_ids,
                captured_samples,
                first_utc_ns,
                finalized_utc_ns,
                compression,
                stream_receipt,
            )
        )
        verification_error = None
        try:
            verification = self.store.verify(published)
            digest_valid = True
        except Exception as error:
            verification = None
            digest_valid = False
            verification_error = f"{type(error).__name__}: {error}"
        uncompressed_bytes = (
            stream_receipt.captured_sample_count * config.receiver_count * 4
            if verification is None
            else verification.uncompressed_bytes
        )
        compressed_bytes = (
            sum(chunk.compressed_bytes for chunk in stream_receipt.chunks)
            if verification is None
            else verification.compressed_bytes
        )
        throughput = uncompressed_bytes / 1_000_000 / elapsed_seconds
        result = WriterBenchmarkReceiptV1(
            benchmark_id=benchmark_id,
            configuration=config,
            created_utc_ns=created_utc_ns,
            finalized_utc_ns=max(created_utc_ns, finalized_utc_ns),
            cancelled=event.is_set(),
            passed=(
                not event.is_set() and digest_valid and throughput >= config.minimum_throughput_mb_s
            ),
            bundle_uri=published.uri,
            manifest_sha256=published.manifest_sha256,
            digest_valid=digest_valid,
            elapsed_seconds=elapsed_seconds,
            block_count=block_count,
            uncompressed_bytes=uncompressed_bytes,
            compressed_bytes=compressed_bytes,
            compression_ratio=(uncompressed_bytes / compressed_bytes if compressed_bytes else None),
            throughput_mb_s=throughput,
            error=verification_error,
        )
        _atomic_write_model(receipt_path, result)
        return result


def _qualification_receipt(
    plan: CapturePlanV1,
    qualification_id: str,
    requested_trial_count: int,
    policy: AcquisitionAcceptancePolicyV1,
    created_utc_ns: int,
    updated_utc_ns: int,
    cancelled: bool,
    trials: tuple[QualificationTrialV1, ...],
) -> AcquisitionQualificationReceiptV1:
    aggregate = _aggregate(trials, requested_trial_count, policy)
    complete = len(trials) == requested_trial_count
    dual = len(plan.radio_ids) == 2
    passed = (
        complete
        and not cancelled
        and aggregate.successful_trial_fraction >= policy.minimum_successful_trial_fraction
        and (
            not dual
            or aggregate.overlap_passing_trial_fraction
            >= policy.minimum_overlap_passing_trial_fraction
        )
        and aggregate.false_complete_count <= policy.maximum_false_complete_count
        and aggregate.false_coherent_count <= policy.maximum_false_coherent_count
        and (not policy.require_all_digests_valid or aggregate.all_digests_valid)
    )
    return AcquisitionQualificationReceiptV1(
        qualification_id=qualification_id,
        profile_name=plan.profile_revision.profile.name,
        profile_revision_digest=plan.profile_revision.revision_digest,
        capture_plan_digest=plan.plan_digest,
        radio_ids=plan.radio_ids,
        requested_trial_count=requested_trial_count,
        policy=policy,
        created_utc_ns=created_utc_ns,
        updated_utc_ns=max(created_utc_ns, updated_utc_ns),
        cancelled=cancelled,
        complete=complete,
        passed=passed,
        trials=trials,
        aggregate=aggregate,
    )


def _aggregate(
    trials: tuple[QualificationTrialV1, ...],
    requested_trial_count: int,
    policy: AcquisitionAcceptancePolicyV1,
) -> AcquisitionAggregateV1:
    committed = sum(trial.state is CaptureState.COMMITTED for trial in trials)
    degraded = sum(trial.state is CaptureState.DEGRADED for trial in trials)
    failed = sum(trial.state is CaptureState.FAILED for trial in trials)
    successful_trials = tuple(
        trial
        for trial in trials
        if trial.state is CaptureState.COMMITTED
        and trial.digest_valid is True
        and trial.false_complete_count == 0
        and trial.false_coherent_count == 0
    )
    overlap_passing = sum(
        trial.overlap_fraction is not None
        and trial.overlap_fraction >= policy.minimum_estimated_overlap_fraction
        for trial in successful_trials
    )
    skew = _present(trials, "estimated_start_skew_ns")
    uncertainty = _present(trials, "start_skew_uncertainty_ns")
    estimated_overlap = _present(trials, "estimated_overlap_ns")
    guaranteed_overlap = _present(trials, "guaranteed_overlap_ns")
    overlap_fraction = _present(trials, "overlap_fraction")
    throughput = _present(trials, "acquisition_throughput_mb_s")
    total_uncompressed = sum(trial.uncompressed_bytes for trial in trials)
    total_compressed = sum(trial.compressed_bytes for trial in trials)
    bundle_trials = tuple(trial for trial in trials if trial.bundle_uri is not None)
    inspection_failure_count = sum(
        any("bundle inspection failed" in error for error in trial.errors) for trial in trials
    )
    return AcquisitionAggregateV1(
        requested_trial_count=requested_trial_count,
        completed_trial_count=len(trials),
        committed_count=committed,
        degraded_count=degraded,
        failed_count=failed,
        successful_count=len(successful_trials),
        successful_trial_fraction=len(successful_trials) / requested_trial_count,
        overlap_passing_count=overlap_passing,
        overlap_passing_trial_fraction=(
            overlap_passing / len(successful_trials) if successful_trials else 0
        ),
        digest_valid_count=sum(trial.digest_valid is True for trial in trials),
        digest_invalid_count=(
            sum(trial.digest_valid is False for trial in trials) + inspection_failure_count
        ),
        all_digests_valid=(
            inspection_failure_count == 0
            and all(trial.digest_valid is True for trial in bundle_trials)
        ),
        total_gap_count=sum(trial.gap_count for trial in trials),
        total_overflow_count=sum(trial.overflow_count for trial in trials),
        false_complete_count=sum(trial.false_complete_count for trial in trials),
        false_coherent_count=sum(trial.false_coherent_count for trial in trials),
        mean_estimated_start_skew_ns=_mean(skew),
        maximum_estimated_start_skew_ns=None if not skew else round(max(skew)),
        mean_start_skew_uncertainty_ns=_mean(uncertainty),
        maximum_start_skew_uncertainty_ns=None if not uncertainty else round(max(uncertainty)),
        mean_estimated_overlap_ns=_mean(estimated_overlap),
        mean_guaranteed_overlap_ns=_mean(guaranteed_overlap),
        mean_overlap_fraction=_mean(overlap_fraction),
        minimum_overlap_fraction=None if not overlap_fraction else min(overlap_fraction),
        total_uncompressed_bytes=total_uncompressed,
        total_compressed_bytes=total_compressed,
        compression_ratio=(total_uncompressed / total_compressed if total_compressed else None),
        mean_acquisition_throughput_mb_s=_mean(throughput),
        minimum_acquisition_throughput_mb_s=None if not throughput else min(throughput),
    )


def _present(
    trials: tuple[QualificationTrialV1, ...],
    field: str,
) -> tuple[float, ...]:
    return tuple(float(value) for trial in trials if (value := getattr(trial, field)) is not None)


def _mean(values: tuple[float, ...]) -> float | None:
    return None if not values else math.fsum(values) / len(values)


def _trial_id(qualification_id: str, index: int) -> str:
    return f"{qualification_id}-trial-{index + 1:06d}"


def _generated_ci16(
    sample_count: int,
    receiver_count: int,
    seed: int,
) -> np.ndarray:
    generator = np.random.Generator(np.random.PCG64(seed))
    return generator.integers(
        -32_768,
        32_768,
        size=(sample_count, receiver_count, 2),
        dtype=np.int16,
    ).astype("<i2", copy=False)


def _benchmark_manifest(
    session_id: str,
    identity: RadioIdentityV1,
    receiver_ids: tuple[int, ...],
    sample_count: int,
    created_utc_ns: int,
    finalized_utc_ns: int,
    compression: CompressionSettingsV1,
    receipt: StreamWriteReceipt,
) -> RecordingManifestV1:
    gains = tuple(ReceiverGainV1(receiver_id=receiver, gain_db=0) for receiver in receiver_ids)
    profile = CaptureProfileV1(
        name="generated-writer-benchmark",
        center_frequency_hz=1_000_000_000,
        sample_rate_hz=2_500_000,
        bandwidth_hz=2_500_000,
        receivers=receiver_ids,
        gain_mode=GainMode.MANUAL,
        gains=gains,
        sample_count=sample_count,
        refill_samples=min(sample_count, 262_144),
        settle_seconds=Decimal(0),
        prime_refills=0,
        synchronization_mode=SynchronizationMode.NONE,
        storage_policy=compression.policy_id,
        tags=("QUALIFICATION", "TEST"),
    )
    plan = compile_capture_plan(
        CaptureProfileRevisionV1.from_profile(profile),
        (identity.radio_id,),
        source_type=SourceType.TEST,
    )
    settings = RadioSettingsV1(
        center_frequency_hz=profile.center_frequency_hz,
        sample_rate_hz=profile.sample_rate_hz,
        bandwidth_hz=profile.bandwidth_hz,
        receiver_ids=receiver_ids,
        gain_mode=GainMode.MANUAL,
        gains=gains,
    )
    timing = StreamTimingV1(
        first_sample=TimingEstimateV1(
            estimate_utc_ns=created_utc_ns,
            earliest_utc_ns=created_utc_ns,
            latest_utc_ns=created_utc_ns,
            method=TimingMethod.HOST_BRACKET,
        ),
        last_sample=TimingEstimateV1(
            estimate_utc_ns=finalized_utc_ns,
            earliest_utc_ns=finalized_utc_ns,
            latest_utc_ns=finalized_utc_ns,
            method=TimingMethod.HOST_BRACKET,
        ),
    )
    stream = RecordingStreamV1(
        stream_id="stream-0",
        radio=identity,
        requested_settings=settings,
        applied_settings=settings,
        state=StreamState.COMPLETE,
        requested_sample_count=sample_count,
        captured_sample_count=sample_count,
        timing=timing,
        chunks=receipt.chunks,
        timeline_relative_path=receipt.timeline_relative_path,
        timeline_sha256=receipt.timeline_sha256,
        continuity=receipt.continuity,
    )
    return RecordingManifestV1(
        session_id=session_id,
        state=CaptureState.COMMITTED,
        source_type=SourceType.TEST,
        created_utc_ns=created_utc_ns,
        finalized_utc_ns=finalized_utc_ns,
        capture_plan=plan,
        tags=("QUALIFICATION", "TEST"),
        streams=(stream,),
        synchronization=SynchronizationSummaryV1(
            requested_mode=SynchronizationMode.NONE,
            effective_mode=SynchronizationMode.NONE,
            grade=SynchronizationGrade.NOT_REQUESTED,
            stream_ids=("stream-0",),
        ),
        compression=compression,
        host=HostIdentityV1(hostname=socket.gethostname(), operating_system=platform.platform()),
        producer=ProducerV1(name="leo-writer-benchmark", version="1"),
    )


def _atomic_write_model(path: Path, model: BaseModel) -> None:
    _reject_qnap_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}-{uuid4().hex}.partial")
    payload = model.model_dump_json(indent=2).encode("utf-8")
    with temporary.open("xb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    descriptor = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _reject_qnap_path(path: Path) -> None:
    resolved = path.resolve(strict=False)
    qnap = Path("/mnt/qnap01")
    if resolved == qnap or qnap in resolved.parents:
        raise ValueError("qualification outputs cannot be written beneath read-only /mnt/qnap01")
