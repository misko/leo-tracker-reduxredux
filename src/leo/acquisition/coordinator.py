"""Profile-driven, bounded single/paired-radio acquisition coordination."""

from __future__ import annotations

import math
import platform
import shutil
import socket
import threading
import time
from collections.abc import Callable, Mapping
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from threading import Event
from typing import Literal

from leo.acquisition.clock import AcquisitionClock, SystemAcquisitionClock
from leo.acquisition.errors import AcquisitionCancelled, AcquisitionError
from leo.acquisition.models import (
    AcquisitionConfig,
    AdmissionEstimate,
    CaptureSessionResult,
    StorageAdmissionDecision,
)
from leo.contracts.profile import CapturePlanV1
from leo.contracts.radio import IqBlockMetadataV1, RadioIdentityV1, RadioSettingsV1
from leo.contracts.recording import (
    CompressionSettingsV1,
    ContinuitySummaryV1,
    HostIdentityV1,
    ProducerV1,
    RecordingChunkV1,
    RecordingManifestV1,
    RecordingStreamV1,
    StreamTimingV1,
    SynchronizationSummaryV1,
    TimingEstimateV1,
)
from leo.contracts.states import (
    CaptureState,
    ContinuityPolicy,
    ContinuityStatus,
    PeerFailurePolicy,
    StreamState,
    SynchronizationGrade,
    SynchronizationMode,
)
from leo.domain.iq import IqBlock
from leo.radio.ports import RadioSource
from leo.storage import RecordingStore
from leo.storage.writer import (
    PublishedBundle,
    RecordingBundleWriter,
    StreamWriteReceipt,
)

FreeBytes = Callable[[Path], int]
StorageAdmission = Callable[[Path], StorageAdmissionDecision]


@dataclass(frozen=True, slots=True)
class _PreparedRadio:
    index: int
    stream_id: str
    source: RadioSource
    identity: RadioIdentityV1
    requested_settings: RadioSettingsV1
    applied_settings: RadioSettingsV1


@dataclass(frozen=True, slots=True)
class _StreamOutcome:
    index: int
    stream_id: str
    identity: RadioIdentityV1
    requested_settings: RadioSettingsV1
    applied_settings: RadioSettingsV1 | None
    state: StreamState
    captured_sample_count: int
    receipt: StreamWriteReceipt | None
    timing: StreamTimingV1 | None
    error: str | None
    storage_fatal: bool = False


class _ReadinessGate:
    """One-shot barrier whose coordinator supplies the common release target."""

    def __init__(self, expected: int) -> None:
        self._expected = expected
        self._ready = 0
        self._target: int | None = None
        self._error: str | None = None
        self._condition = threading.Condition()

    def arrive_and_wait(self, cancel: Event) -> int:
        with self._condition:
            self._ready += 1
            self._condition.notify_all()
            while self._target is None and self._error is None:
                if cancel.is_set():
                    raise AcquisitionCancelled("capture cancelled at readiness barrier")
                self._condition.wait(timeout=0.05)
            if self._error is not None:
                raise AcquisitionError(self._error)
            assert self._target is not None
            return self._target

    def wait_until_ready(self, timeout_seconds: float, cancel: Event) -> None:
        deadline = time.monotonic() + timeout_seconds
        with self._condition:
            while self._ready < self._expected and self._error is None:
                if cancel.is_set():
                    raise AcquisitionCancelled("capture cancelled before all radios were ready")
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise AcquisitionError("radio readiness barrier timed out")
                self._condition.wait(timeout=min(remaining, 0.05))
            if self._error is not None:
                raise AcquisitionError(self._error)

    def release(self, target_monotonic_ns: int) -> None:
        with self._condition:
            self._target = target_monotonic_ns
            self._condition.notify_all()

    def abort(self, error: str) -> None:
        with self._condition:
            self._error = error
            self._condition.notify_all()


class AcquisitionCoordinator:
    """Prepare radios concurrently, release together, stream bounded IQ, publish last."""

    def __init__(
        self,
        store: RecordingStore,
        *,
        compression: CompressionSettingsV1 | None = None,
        clock: AcquisitionClock | None = None,
        config: AcquisitionConfig | None = None,
        free_bytes: FreeBytes | None = None,
        storage_admission: StorageAdmission | None = None,
        host: HostIdentityV1 | None = None,
        producer: ProducerV1 | None = None,
    ) -> None:
        self.store = store
        self._compression = compression
        self.clock = clock or SystemAcquisitionClock()
        self.config = config or AcquisitionConfig()
        self._free_bytes = free_bytes or (lambda path: shutil.disk_usage(path).free)
        self._storage_admission = storage_admission or (
            lambda _path: StorageAdmissionDecision(allowed=True)
        )
        self._host = host or HostIdentityV1(
            hostname=socket.gethostname(),
            operating_system=platform.platform(),
        )
        self._producer = producer or ProducerV1(name="leo-acquisition", version="0.1.0")

    def estimate_admission(self, plan: CapturePlanV1) -> AdmissionEstimate:
        profile = plan.profile_revision.profile
        radio_count = len(plan.radio_ids)
        raw_bytes = plan.resolved_sample_count * len(profile.receivers) * 4 * radio_count
        refill_count = math.ceil(plan.resolved_sample_count / profile.refill_samples)
        metadata_bytes = refill_count * radio_count * self.config.metadata_bytes_per_refill
        required = raw_bytes + metadata_bytes + self.config.safety_reserve_bytes
        available = max(0, int(self._free_bytes(self.store.root)))
        policy = self._storage_admission(self.store.root)
        return AdmissionEstimate(
            raw_iq_bytes=raw_bytes,
            metadata_reserve_bytes=metadata_bytes,
            safety_reserve_bytes=self.config.safety_reserve_bytes,
            required_free_bytes=required,
            available_free_bytes=available,
            admitted=available >= required and policy.allowed,
            storage_used_fraction=policy.used_fraction,
            storage_warning=policy.warning,
            policy_reason=policy.reason,
        )

    def capture_once(
        self,
        plan: CapturePlanV1,
        sources: Mapping[str, RadioSource],
        *,
        session_id: str,
        cancel: Event | None = None,
        extra_tags: tuple[str, ...] = (),
        requested_settings_by_radio: Mapping[str, RadioSettingsV1] | None = None,
    ) -> CaptureSessionResult:
        external_cancel = cancel or Event()
        admission = self.estimate_admission(plan)
        if not admission.admitted:
            policy_detail = (
                f"; {admission.policy_reason}" if admission.policy_reason is not None else ""
            )
            return self._failed_result(
                session_id,
                admission,
                f"storage admission rejected: need {admission.required_free_bytes} free bytes, "
                f"have {admission.available_free_bytes}{policy_detail}",
            )
        try:
            ordered_sources = self._validate_sources(plan, sources)
            compression = self._compression_for(plan)
        except Exception as error:
            return self._failed_result(session_id, admission, _error_text(error))
        if external_cancel.is_set():
            return self._failed_result(session_id, admission, "capture cancelled before prepare")

        created_utc_ns = self.clock.utc_ns()
        default_settings = _settings_from_plan(plan)
        requested_settings = _requested_settings_by_radio(
            plan,
            default_settings,
            requested_settings_by_radio,
        )
        prepared, prep_failures = self._prepare_all(
            plan,
            ordered_sources,
            requested_settings,
            external_cancel,
        )
        if not prepared:
            return self._failed_result(session_id, admission, *prep_failures.values())
        fail_whole = (
            len(plan.radio_ids) == 2
            and plan.profile_revision.profile.peer_failure_policy is PeerFailurePolicy.FAIL_SESSION
        )
        if prep_failures and fail_whole:
            _close_sources(tuple(item.source for item in prepared.values()))
            return self._failed_result(session_id, admission, *prep_failures.values())
        if external_cancel.is_set():
            _close_sources(tuple(item.source for item in prepared.values()))
            return self._failed_result(session_id, admission, "capture cancelled during prepare")

        try:
            bundle_writer = self.store.begin(session_id, compression)
        except Exception as error:
            _close_sources(tuple(item.source for item in prepared.values()))
            return self._failed_result(session_id, admission, _error_text(error))

        session_cancel = Event()
        gate = _ReadinessGate(len(prepared))
        capture_futures: dict[int, Future[_StreamOutcome]] = {}
        release_target: int | None = None
        errors: list[str] = list(prep_failures.values())
        with ThreadPoolExecutor(
            max_workers=len(prepared),
            thread_name_prefix="leo-capture",
        ) as pool:
            for index, item in prepared.items():
                capture_futures[index] = pool.submit(
                    self._capture_radio,
                    item,
                    plan,
                    bundle_writer,
                    gate,
                    external_cancel,
                    session_cancel,
                    fail_whole,
                )
            try:
                gate.wait_until_ready(self.config.readiness_timeout_seconds, external_cancel)
                release_target = self.clock.monotonic_ns() + self.config.release_lead_ns
                gate.release(release_target)
            except Exception as error:
                errors.append(_error_text(error))
                session_cancel.set()
                gate.abort(_error_text(error))

        outcomes: dict[int, _StreamOutcome] = {}
        for index, future in capture_futures.items():
            try:
                outcome = future.result()
            except Exception as error:
                item = prepared[index]
                outcome = _failed_outcome(item, _error_text(error), storage_fatal=True)
            outcomes[index] = outcome
            if outcome.error is not None:
                errors.append(f"{outcome.identity.radio_id}: {outcome.error}")

        errors.extend(_close_sources(tuple(item.source for item in prepared.values())))
        for index, preparation_error in prep_failures.items():
            outcomes[index] = _failed_outcome_from_source(
                index,
                ordered_sources[index],
                requested_settings[plan.radio_ids[index]],
                preparation_error,
            )
        ordered_outcomes = tuple(outcomes[index] for index in range(len(plan.radio_ids)))
        any_storage_fatal = any(outcome.storage_fatal for outcome in ordered_outcomes)
        any_data = any(outcome.captured_sample_count for outcome in ordered_outcomes)
        capture_failed = any(
            outcome.state is not StreamState.COMPLETE for outcome in ordered_outcomes
        )
        cancelled = external_cancel.is_set()
        if any_storage_fatal or not any_data or cancelled or (fail_whole and capture_failed):
            bundle_writer.close()
            if cancelled:
                errors.append("capture cancelled; no manifest was published")
            if fail_whole and capture_failed:
                errors.append("peer-failure policy rejected a partial paired capture")
            return CaptureSessionResult(
                session_id=session_id,
                state=CaptureState.FAILED,
                admission=admission,
                release_target_monotonic_ns=release_target,
                errors=_canonical_errors(errors),
            )

        try:
            streams = tuple(_recording_stream(plan, outcome) for outcome in ordered_outcomes)
            state: Literal[CaptureState.COMMITTED, CaptureState.DEGRADED] = (
                CaptureState.COMMITTED
                if all(stream.state is StreamState.COMPLETE for stream in streams)
                else CaptureState.DEGRADED
            )
            synchronization = _synchronization_summary(plan, streams, release_target)
            manifest = RecordingManifestV1(
                session_id=session_id,
                state=state,
                source_type=plan.source_type,
                created_utc_ns=created_utc_ns,
                finalized_utc_ns=max(created_utc_ns, self.clock.utc_ns()),
                capture_plan=plan,
                tags=tuple(sorted(set(plan.profile_revision.profile.tags) | set(extra_tags))),
                streams=streams,
                synchronization=synchronization,
                compression=compression,
                host=self._host,
                producer=self._producer,
            )
            published = self._publish_or_recover(bundle_writer, manifest, errors)
            return CaptureSessionResult(
                session_id=session_id,
                state=manifest.state,
                admission=admission,
                bundle=published,
                manifest=published.manifest,
                release_target_monotonic_ns=release_target,
                errors=_canonical_errors(errors),
            )
        except Exception as error:
            bundle_writer.close()
            errors.append(_error_text(error))
            return CaptureSessionResult(
                session_id=session_id,
                state=CaptureState.FAILED,
                admission=admission,
                release_target_monotonic_ns=release_target,
                errors=_canonical_errors(errors),
            )

    def _compression_for(self, plan: CapturePlanV1) -> CompressionSettingsV1:
        policy_id = plan.profile_revision.profile.storage_policy
        if self._compression is None:
            return CompressionSettingsV1(policy_id=policy_id)
        if self._compression.policy_id != policy_id:
            raise ValueError(
                f"configured compression policy {self._compression.policy_id!r} does not match "
                f"profile policy {policy_id!r}"
            )
        return self._compression

    @staticmethod
    def _validate_sources(
        plan: CapturePlanV1,
        sources: Mapping[str, RadioSource],
    ) -> tuple[RadioSource, ...]:
        expected = set(plan.radio_ids)
        if set(sources) != expected:
            missing = sorted(expected - set(sources))
            extra = sorted(set(sources) - expected)
            raise ValueError(f"radio source mapping mismatch; missing={missing}, extra={extra}")
        ordered = tuple(sources[radio_id] for radio_id in plan.radio_ids)
        for radio_id, source in zip(plan.radio_ids, ordered, strict=True):
            if source.identity.radio_id != radio_id:
                raise ValueError(
                    f"source identity {source.identity.radio_id!r} != plan {radio_id!r}"
                )
        return ordered

    def _prepare_all(
        self,
        plan: CapturePlanV1,
        sources: tuple[RadioSource, ...],
        requested_settings: Mapping[str, RadioSettingsV1],
        cancel: Event,
    ) -> tuple[dict[int, _PreparedRadio], dict[int, str]]:
        prepared: dict[int, _PreparedRadio] = {}
        failures: dict[int, str] = {}
        with ThreadPoolExecutor(max_workers=len(sources), thread_name_prefix="leo-prepare") as pool:
            futures = {
                index: pool.submit(
                    self._prepare_radio,
                    index,
                    source,
                    plan.radio_ids[index],
                    requested_settings[plan.radio_ids[index]],
                    plan,
                    cancel,
                )
                for index, source in enumerate(sources)
            }
            for index, future in futures.items():
                try:
                    prepared[index] = future.result()
                except Exception as error:
                    failures[index] = (
                        f"{plan.radio_ids[index]} prepare failed: {_error_text(error)}"
                    )
        return prepared, failures

    def _prepare_radio(
        self,
        index: int,
        source: RadioSource,
        expected_radio_id: str,
        requested_settings: RadioSettingsV1,
        plan: CapturePlanV1,
        cancel: Event,
    ) -> _PreparedRadio:
        try:
            identity = source.open()
            if identity.radio_id != expected_radio_id or source.identity != identity:
                raise AcquisitionError(
                    "opened radio identity does not match its attested plan slot"
                )
            capabilities = source.capabilities
            if any(
                receiver not in capabilities.receiver_ids
                for receiver in requested_settings.receiver_ids
            ):
                raise AcquisitionError("radio does not support every requested receiver")
            if not (
                capabilities.minimum_sample_rate_hz
                <= requested_settings.sample_rate_hz
                <= capabilities.maximum_sample_rate_hz
            ):
                raise AcquisitionError("radio does not support the requested sample rate")
            actual = source.configure(requested_settings)
            _validate_settings_readback(requested_settings, actual)
            self.clock.sleep(float(plan.profile_revision.profile.settle_seconds), cancel)
            for _ in range(plan.profile_revision.profile.prime_refills):
                if cancel.is_set():
                    raise AcquisitionCancelled("capture cancelled while priming")
                source.read_block(plan.profile_revision.profile.refill_samples)
            return _PreparedRadio(
                index,
                f"stream-{index}",
                source,
                identity,
                requested_settings,
                actual,
            )
        except BaseException:
            with suppress(Exception):
                source.close()
            raise

    def _capture_radio(
        self,
        item: _PreparedRadio,
        plan: CapturePlanV1,
        bundle: RecordingBundleWriter,
        gate: _ReadinessGate,
        external_cancel: Event,
        session_cancel: Event,
        fail_whole: bool,
    ) -> _StreamOutcome:
        receipt: StreamWriteReceipt | None = None
        stream_writer = None
        captured = 0
        first_metadata: IqBlockMetadataV1 | None = None
        last_metadata: IqBlockMetadataV1 | None = None
        release_observed: int | None = None
        release_target: int | None = None
        error_text: str | None = None
        storage_fatal = False
        try:
            release_target = gate.arrive_and_wait(external_cancel)
            release_observed = self.clock.wait_until(release_target, external_cancel)
            requested = plan.resolved_sample_count
            refill = plan.profile_revision.profile.refill_samples
            while captured < requested:
                if external_cancel.is_set() or (fail_whole and session_cancel.is_set()):
                    raise AcquisitionCancelled("capture cancelled at a refill boundary")
                count = min(refill, requested - captured)
                block = item.source.read_block(count)
                block = _validate_and_rebase_block(block, item, count, captured)
                if (
                    plan.profile_revision.profile.continuity_policy
                    is ContinuityPolicy.REQUIRE_CONTIGUOUS
                    and block.metadata.continuity
                    in {ContinuityStatus.GAP_BEFORE, ContinuityStatus.OVERFLOW}
                ):
                    raise AcquisitionError(
                        f"continuity policy rejected {block.metadata.continuity.value} "
                        f"before sample {captured}"
                    )
                if stream_writer is None:
                    stream_writer = bundle.open_stream(
                        item.stream_id,
                        item.identity,
                        item.applied_settings.receiver_ids,
                    )
                stream_writer.append(block)
                if first_metadata is None:
                    first_metadata = block.metadata
                last_metadata = block.metadata
                captured += count
        except Exception as error:
            error_text = _error_text(error)
            if fail_whole:
                session_cancel.set()
        finally:
            if stream_writer is not None:
                try:
                    receipt = stream_writer.finalize()
                except Exception as error:
                    storage_fatal = True
                    error_text = f"storage finalization failed: {_error_text(error)}"
                    if fail_whole:
                        session_cancel.set()

        timing = None
        if first_metadata is not None and last_metadata is not None:
            assert release_target is not None and release_observed is not None
            timing = _stream_timing(
                first_metadata,
                last_metadata,
                item.applied_settings.sample_rate_hz,
                captured,
                release_target,
                release_observed,
            )
        if error_text is None and captured == plan.resolved_sample_count:
            state = StreamState.COMPLETE
        elif captured:
            state = StreamState.PARTIAL
            error_text = error_text or "capture ended before the requested sample count"
        else:
            state = StreamState.FAILED
            error_text = error_text or "radio produced no accepted IQ samples"
        return _StreamOutcome(
            index=item.index,
            stream_id=item.stream_id,
            identity=item.identity,
            requested_settings=item.requested_settings,
            applied_settings=item.applied_settings,
            state=state,
            captured_sample_count=captured,
            receipt=receipt,
            timing=timing,
            error=error_text,
            storage_fatal=storage_fatal,
        )

    def _publish_or_recover(
        self,
        writer: RecordingBundleWriter,
        manifest: RecordingManifestV1,
        errors: list[str],
    ) -> PublishedBundle:
        try:
            return writer.publish(manifest)
        except Exception as error:
            if writer.published_path is None:
                raise
            recovered = self.store.inspect(manifest.session_id)
            errors.append(
                f"publication durability warning after atomic rename: {_error_text(error)}"
            )
            return recovered

    @staticmethod
    def _failed_result(
        session_id: str,
        admission: AdmissionEstimate,
        *errors: str,
    ) -> CaptureSessionResult:
        return CaptureSessionResult(
            session_id=session_id,
            state=CaptureState.FAILED,
            admission=admission,
            errors=_canonical_errors(errors),
        )


def _settings_from_plan(plan: CapturePlanV1) -> RadioSettingsV1:
    profile = plan.profile_revision.profile
    return RadioSettingsV1(
        center_frequency_hz=profile.center_frequency_hz,
        sample_rate_hz=profile.sample_rate_hz,
        bandwidth_hz=profile.bandwidth_hz,
        receiver_ids=profile.receivers,
        gain_mode=profile.gain_mode,
        gains=profile.gains,
    )


def _requested_settings_by_radio(
    plan: CapturePlanV1,
    default: RadioSettingsV1,
    overrides: Mapping[str, RadioSettingsV1] | None,
) -> dict[str, RadioSettingsV1]:
    if overrides is None:
        return dict.fromkeys(plan.radio_ids, default)
    if set(overrides) != set(plan.radio_ids):
        raise ValueError("per-radio settings must exactly cover capture-plan radios")
    variable_fields = {"center_frequency_hz", "gain_mode", "gains"}
    expected_geometry = default.model_dump(exclude=variable_fields)
    result: dict[str, RadioSettingsV1] = {}
    for radio_id in plan.radio_ids:
        settings = overrides[radio_id]
        if settings.model_dump(exclude=variable_fields) != expected_geometry:
            raise ValueError(
                "per-radio settings may override only center frequency and gain configuration"
            )
        result[radio_id] = settings
    return result


def _validate_settings_readback(
    requested: RadioSettingsV1,
    actual: RadioSettingsV1,
) -> None:
    for field in ("center_frequency_hz", "sample_rate_hz", "bandwidth_hz"):
        expected_value = int(getattr(requested, field))
        actual_value = int(getattr(actual, field))
        if abs(actual_value - expected_value) > max(1, round(expected_value * 1e-6)):
            raise AcquisitionError(
                f"radio {field} readback mismatch: requested {expected_value}, got {actual_value}"
            )
    if requested.receiver_ids != actual.receiver_ids:
        raise AcquisitionError("radio receiver readback mismatch")
    if requested.gain_mode is not actual.gain_mode or requested.gains != actual.gains:
        raise AcquisitionError("radio gain readback mismatch")


def _validate_and_rebase_block(
    block: IqBlock,
    item: _PreparedRadio,
    expected_count: int,
    sample_start: int,
) -> IqBlock:
    metadata = block.metadata
    if metadata.radio_id != item.identity.radio_id:
        raise AcquisitionError("radio returned a block for a different identity")
    if metadata.receiver_ids != item.applied_settings.receiver_ids:
        raise AcquisitionError("radio receiver geometry changed during capture")
    if metadata.sample_count != expected_count or block.samples.shape[0] != expected_count:
        raise AcquisitionError("radio returned a short or oversized refill")
    rebased = metadata.model_copy(update={"session_sample_start": sample_start})
    return IqBlock(samples=block.samples, metadata=rebased)


def _stream_timing(
    first: IqBlockMetadataV1,
    last: IqBlockMetadataV1,
    sample_rate_hz: int,
    captured_sample_count: int,
    release_target: int,
    release_observed: int,
) -> StreamTimingV1:
    first_interval = first.host_request_utc_ns
    last_interval = last.host_request_utc_ns
    first_estimate = (first_interval.lower_ns + first_interval.upper_ns) // 2
    nominal_duration_ns = (captured_sample_count - 1) * 1_000_000_000 // sample_rate_hz
    first_block_duration_ns = first.sample_count * 1_000_000_000 // sample_rate_hz
    if first.device_sample_counter is not None and last.device_sample_counter is not None:
        counter_duration_ns = (
            (last.device_sample_counter + last.sample_count - 1 - first.device_sample_counter)
            * 1_000_000_000
            // sample_rate_hz
        )
        last_estimate = first_estimate + counter_duration_ns
        last_earliest = max(0, first_interval.lower_ns + counter_duration_ns)
        last_latest = first_interval.upper_ns + counter_duration_ns
    else:
        # A host read bracket timestamps the refill operation, not a device sample.
        # Keep the sample-clock estimate nominal but widen its bound through the
        # final observed read, so host/compression lag is never presented as IQ.
        last_estimate = first_estimate + nominal_duration_ns
        first_earliest = max(0, first_interval.lower_ns - first_block_duration_ns)
        last_earliest = first_earliest + nominal_duration_ns
        last_latest = max(
            first_interval.upper_ns + nominal_duration_ns,
            last_interval.upper_ns,
        )
    return StreamTimingV1(
        release_target_monotonic_ns=release_target,
        release_observed_monotonic_ns=release_observed,
        first_sample=TimingEstimateV1(
            estimate_utc_ns=first_estimate,
            earliest_utc_ns=(
                first_interval.lower_ns
                if first.device_sample_counter is not None
                else max(0, first_interval.lower_ns - first_block_duration_ns)
            ),
            latest_utc_ns=first_interval.upper_ns,
            method=first.timing_method,
        ),
        last_sample=TimingEstimateV1(
            estimate_utc_ns=last_estimate,
            earliest_utc_ns=last_earliest,
            latest_utc_ns=last_latest,
            method=last.timing_method,
        ),
    )


def _recording_stream(plan: CapturePlanV1, outcome: _StreamOutcome) -> RecordingStreamV1:
    receipt = outcome.receipt
    chunks: tuple[RecordingChunkV1, ...]
    if outcome.state is StreamState.FAILED:
        continuity = ContinuitySummaryV1(refill_count=0, segment_count=0)
        chunks = ()
        timeline_path = None
        timeline_digest = None
    else:
        if receipt is None:
            raise AcquisitionError("captured stream has no finalized storage receipt")
        continuity = receipt.continuity
        chunks = receipt.chunks
        timeline_path = receipt.timeline_relative_path
        timeline_digest = receipt.timeline_sha256
    return RecordingStreamV1(
        stream_id=outcome.stream_id,
        radio=outcome.identity,
        requested_settings=outcome.requested_settings,
        applied_settings=outcome.applied_settings,
        state=outcome.state,
        requested_sample_count=plan.resolved_sample_count,
        captured_sample_count=outcome.captured_sample_count,
        timing=outcome.timing,
        chunks=chunks,
        timeline_relative_path=timeline_path,
        timeline_sha256=timeline_digest,
        continuity=continuity,
        error=(
            None
            if outcome.state is StreamState.COMPLETE
            else (outcome.error or "capture failed")[:2048]
        ),
    )


def _synchronization_summary(
    plan: CapturePlanV1,
    streams: tuple[RecordingStreamV1, ...],
    release_target: int | None,
) -> SynchronizationSummaryV1:
    stream_ids = tuple(stream.stream_id for stream in streams)
    if plan.effective_synchronization_mode is SynchronizationMode.NONE:
        return SynchronizationSummaryV1(
            requested_mode=plan.requested_synchronization_mode,
            effective_mode=SynchronizationMode.NONE,
            grade=SynchronizationGrade.NOT_REQUESTED,
            stream_ids=stream_ids,
            release_target_monotonic_ns=release_target,
        )
    timed = tuple(stream for stream in streams if stream.timing is not None)
    if len(timed) != 2:
        return SynchronizationSummaryV1(
            requested_mode=plan.requested_synchronization_mode,
            effective_mode=plan.effective_synchronization_mode,
            grade=SynchronizationGrade.DEGRADED,
            stream_ids=stream_ids,
            release_target_monotonic_ns=release_target,
        )
    first_a, first_b = (stream.timing.first_sample for stream in timed if stream.timing)
    duration_a, duration_b = (
        stream.captured_sample_count
        * 1_000_000_000
        // (stream.applied_settings or stream.requested_settings).sample_rate_hz
        for stream in timed
    )
    overlap_start = max(first_a.estimate_utc_ns, first_b.estimate_utc_ns)
    overlap_end = max(
        overlap_start,
        min(
            first_a.estimate_utc_ns + duration_a,
            first_b.estimate_utc_ns + duration_b,
        ),
    )
    estimated_overlap = overlap_end - overlap_start
    continuity_verified = all(
        stream.continuity.sample_loss_observable
        and stream.continuity.gap_count == 0
        and stream.continuity.overflow_count == 0
        for stream in timed
    )
    if continuity_verified:
        guaranteed_start = max(first_a.latest_utc_ns, first_b.latest_utc_ns)
        guaranteed_end = min(
            first_a.earliest_utc_ns + duration_a,
            first_b.earliest_utc_ns + duration_b,
        )
        guaranteed_overlap = max(0, guaranteed_end - guaranteed_start)
    else:
        guaranteed_overlap = 0
    denominator = min(duration_a, duration_b)
    overlap_fraction = 0.0 if denominator == 0 else min(1.0, estimated_overlap / denominator)
    uncertainty = (first_a.latest_utc_ns - first_a.earliest_utc_ns) + (
        first_b.latest_utc_ns - first_b.earliest_utc_ns
    )
    return SynchronizationSummaryV1(
        requested_mode=plan.requested_synchronization_mode,
        effective_mode=plan.effective_synchronization_mode,
        grade=(
            SynchronizationGrade.BEST_EFFORT_OBSERVED
            if continuity_verified
            and all(stream.state is StreamState.COMPLETE for stream in streams)
            else SynchronizationGrade.DEGRADED
        ),
        stream_ids=stream_ids,
        release_target_monotonic_ns=release_target,
        estimated_start_skew_ns=abs(first_a.estimate_utc_ns - first_b.estimate_utc_ns),
        start_skew_uncertainty_ns=uncertainty,
        estimated_overlap_ns=estimated_overlap,
        estimated_overlap_start_utc_ns=overlap_start,
        estimated_overlap_end_utc_ns=overlap_end,
        guaranteed_overlap_ns=guaranteed_overlap,
        overlap_fraction=overlap_fraction,
    )


def _failed_outcome(
    item: _PreparedRadio,
    error: str,
    *,
    storage_fatal: bool = False,
) -> _StreamOutcome:
    return _StreamOutcome(
        index=item.index,
        stream_id=item.stream_id,
        identity=item.identity,
        requested_settings=item.requested_settings,
        applied_settings=item.applied_settings,
        state=StreamState.FAILED,
        captured_sample_count=0,
        receipt=None,
        timing=None,
        error=error,
        storage_fatal=storage_fatal,
    )


def _failed_outcome_from_source(
    index: int,
    source: RadioSource,
    requested_settings: RadioSettingsV1,
    error: str,
) -> _StreamOutcome:
    return _StreamOutcome(
        index=index,
        stream_id=f"stream-{index}",
        identity=source.identity,
        requested_settings=requested_settings,
        applied_settings=None,
        state=StreamState.FAILED,
        captured_sample_count=0,
        receipt=None,
        timing=None,
        error=error,
    )


def _close_sources(sources: tuple[RadioSource, ...]) -> tuple[str, ...]:
    errors: list[str] = []
    for source in sources:
        try:
            source.close()
        except Exception as error:
            errors.append(f"{source.identity.radio_id} close failed: {_error_text(error)}")
    return tuple(errors)


def _error_text(error: BaseException) -> str:
    message = str(error).strip()
    return f"{type(error).__name__}: {message}" if message else type(error).__name__


def _canonical_errors(errors: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(error[:2048] for error in errors if error))
