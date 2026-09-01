"""Profile-driven, bounded single/paired-radio acquisition coordination."""

from __future__ import annotations

import logging
import math
import platform
import queue
import shutil
import socket
import threading
import time
from collections.abc import Callable, Mapping
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from threading import Event
from typing import Literal, cast

from leo.acquisition.clock import AcquisitionClock, SystemAcquisitionClock
from leo.acquisition.coverage import CaptureStreamCoverage, project_capture_progress_coverage
from leo.acquisition.errors import (
    AcquisitionCancelled,
    AcquisitionError,
    AcquisitionSupervisorPoisoned,
)
from leo.acquisition.models import (
    AcquisitionConfig,
    AdmissionEstimate,
    CaptureSessionResult,
    StorageAdmissionDecision,
)
from leo.contracts.device_buffer import (
    DDR_RING_EVIDENCE_KEY_V1,
    DIRECT_ASYNC_EVIDENCE_KEY_V1,
    DIRECT_ASYNC_PROFILE_TAG_V1,
    DIRECT_ASYNC_RAM_DROP_EVIDENCE_KEY_V2,
    DIRECT_ASYNC_RAM_DROP_EVIDENCE_KEY_V3,
    DIRECT_ASYNC_RAM_DROP_PROFILE_TAG_V2,
    DIRECT_ASYNC_RAM_DROP_PROFILE_TAG_V3,
    DdrRingStatusV1,
    DeviceBufferEvidenceV1,
    DeviceBufferRequestV1,
    DirectAsyncEvidence,
    DirectAsyncEvidenceV1,
    DirectAsyncRamDropEvidenceV2,
    DirectAsyncRamDropEvidenceV3,
    DirectAsyncRamDropRequestV2,
    DirectAsyncRamDropRequestV3,
    DirectAsyncRamStatusV2,
    DirectAsyncRequest,
    DirectAsyncRequestV1,
    device_buffer_request,
    device_buffer_request_v1,
)
from leo.contracts.digests import canonical_json_bytes
from leo.contracts.mixed_rate_capture import CapturePlanV3, CapturePlanV4, CapturePlanV5
from leo.contracts.profile import (
    CapturePlanV1,
    CapturePlanV2,
    CaptureProfileV1,
    CaptureProfileV2,
)
from leo.contracts.radio import (
    IqBlockMetadataV1,
    IqBlockMetadataV2,
    RadioIdentityV1,
    RadioSettingsV1,
)
from leo.contracts.recording import (
    DEVICE_AXIS_STORAGE_POLICY_V1,
    CompressionSettingsV1,
    ContinuitySummaryV1,
    ContinuitySummaryV2,
    HostIdentityV1,
    ProducerV1,
    RecordingChunkV1,
    RecordingManifestV1,
    RecordingManifestV2,
    RecordingManifestV3,
    RecordingManifestV4,
    RecordingManifestV5,
    RecordingManifestV6,
    RecordingStreamV1,
    RecordingStreamV2,
    RecordingStreamV3,
    StreamTimingV1,
    SynchronizationSummaryV1,
    TimingEstimateV1,
)
from leo.contracts.states import (
    CaptureState,
    ContinuityPolicy,
    ContinuityStatus,
    PeerFailurePolicy,
    SourceType,
    StreamState,
    SynchronizationGrade,
    SynchronizationMode,
    TimingMethod,
)
from leo.domain.continuity import ContinuityChainValidator
from leo.domain.iq import IqBlock
from leo.radio.ports import RadioSource
from leo.storage import RecordingStore
from leo.storage.staging import RawIqStage
from leo.storage.writer import (
    DeviceAxisStreamBundleWriter,
    DeviceAxisStreamWriteReceipt,
    PublishedBundle,
    RecordingBundleWriter,
    StreamBundleWriter,
    StreamQueueTelemetry,
    StreamWriteReceipt,
)

FreeBytes = Callable[[Path], int]
StorageAdmission = Callable[[Path], StorageAdmissionDecision]
CapturePlan = CapturePlanV1 | CapturePlanV3 | CapturePlanV4 | CapturePlanV5
_LOG = logging.getLogger(__name__)


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
    receipt: StreamWriteReceipt | DeviceAxisStreamWriteReceipt | None
    timing: StreamTimingV1 | None
    error: str | None
    storage_fatal: bool = False
    timed_out_consumer: threading.Thread | None = None
    interruption: BaseException | None = None
    coverage: CaptureStreamCoverage | None = None


@dataclass(frozen=True, slots=True)
class _SourceCloseOutcome:
    errors: tuple[str, ...]
    interruption: BaseException | None


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


class _RfDrainGate:
    """Keep post-RF storage work behind every prepared radio read loop."""

    def __init__(self, expected: int) -> None:
        self._expected = expected
        self._drained = 0
        self._condition = threading.Condition()

    def arrive(self) -> None:
        with self._condition:
            self._drained += 1
            if self._drained > self._expected:
                raise AcquisitionError("RF-drain barrier received too many arrivals")
            self._condition.notify_all()

    def wait_until_drained(self) -> None:
        with self._condition:
            while self._drained < self._expected:
                self._condition.wait(timeout=0.05)


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

    def estimate_admission(self, plan: CapturePlan) -> AdmissionEstimate:
        geometry = tuple(_radio_geometry(plan, radio_id) for radio_id in plan.radio_ids)
        raw_bytes = sum(
            sample_count * len(profile.receivers) * 4
            for profile, sample_count, _settings in geometry
        )
        metadata_bytes = sum(
            math.ceil(sample_count / profile.refill_samples) * self.config.metadata_bytes_per_refill
            for profile, sample_count, _settings in geometry
        )
        staging_bytes = sum(
            sample_count * len(profile.receivers) * 4
            for profile, sample_count, _settings in geometry
            if profile.storage_policy == DEVICE_AXIS_STORAGE_POLICY_V1
        )
        required = raw_bytes + staging_bytes + metadata_bytes + self.config.safety_reserve_bytes
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
        plan: CapturePlan,
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
        requested_settings = _requested_settings_by_radio(
            plan,
            requested_settings_by_radio,
        )
        prepared, prep_failures, preparation_interruption = self._prepare_all(
            plan,
            ordered_sources,
            requested_settings,
            external_cancel,
        )
        if preparation_interruption is not None:
            _close_sources(tuple(item.source for item in prepared.values()))
            raise preparation_interruption
        if not prepared:
            return self._failed_result(session_id, admission, *prep_failures.values())
        fail_whole = len(plan.radio_ids) == 2 and _peer_failure_policy(plan) is (
            PeerFailurePolicy.FAIL_SESSION
        )
        if prep_failures and fail_whole:
            closed = _close_sources(tuple(item.source for item in prepared.values()))
            _raise_source_close_interruption(closed)
            return self._failed_result(
                session_id,
                admission,
                *prep_failures.values(),
                *closed.errors,
            )
        if external_cancel.is_set():
            closed = _close_sources(tuple(item.source for item in prepared.values()))
            _raise_source_close_interruption(closed)
            return self._failed_result(
                session_id,
                admission,
                "capture cancelled during prepare",
                *closed.errors,
            )

        try:
            bundle_writer = self.store.begin(session_id, compression)
        except BaseException as error:
            closed = _close_sources(tuple(item.source for item in prepared.values()))
            if not isinstance(error, Exception):
                raise error
            _raise_source_close_interruption(closed)
            return self._failed_result(
                session_id,
                admission,
                _error_text(error),
                *closed.errors,
            )

        device_axis_capture = _device_axis_capture(plan)
        session_cancel = Event()
        gate = _ReadinessGate(len(prepared))
        rf_drain_gate = _RfDrainGate(len(prepared))
        capture_futures: dict[int, Future[_StreamOutcome]] = {}
        release_target: int | None = None
        errors: list[str] = list(prep_failures.values())
        lifecycle_interruption: BaseException | None = None
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
                    rf_drain_gate,
                    external_cancel,
                    session_cancel,
                    fail_whole,
                )
            try:
                gate.wait_until_ready(self.config.readiness_timeout_seconds, external_cancel)
                release_target = self.clock.monotonic_ns() + self.config.release_lead_ns
                gate.release(release_target)
            except BaseException as error:
                errors.append(_error_text(error))
                session_cancel.set()
                gate.abort(_error_text(error))
                if not isinstance(error, Exception):
                    lifecycle_interruption = error

        outcomes: dict[int, _StreamOutcome] = {}
        for index, future in capture_futures.items():
            try:
                outcome = future.result()
            except BaseException as error:
                item = prepared[index]
                outcome = _failed_outcome(
                    item,
                    _error_text(error),
                    storage_fatal=True,
                    interruption=(error if not isinstance(error, Exception) else None),
                )
            outcomes[index] = outcome
            if outcome.error is not None:
                errors.append(f"{outcome.identity.radio_id}: {outcome.error}")
            if lifecycle_interruption is None and outcome.interruption is not None:
                lifecycle_interruption = outcome.interruption

        closed = _close_sources(tuple(item.source for item in prepared.values()))
        errors.extend(closed.errors)
        if lifecycle_interruption is None:
            lifecycle_interruption = closed.interruption
        for index, preparation_error in prep_failures.items():
            outcomes[index] = _failed_outcome_from_source(
                index,
                ordered_sources[index],
                requested_settings[plan.radio_ids[index]],
                preparation_error,
            )
        ordered_outcomes = tuple(outcomes[index] for index in range(len(plan.radio_ids)))
        timed_out_consumers = tuple(
            outcome.timed_out_consumer
            for outcome in ordered_outcomes
            if outcome.timed_out_consumer is not None
        )
        if timed_out_consumers and plan.source_type is SourceType.LIVE:
            _preserve_failed_bundle(bundle_writer, quarantine=device_axis_capture)
            raise AcquisitionSupervisorPoisoned(
                session_id=session_id,
                consumer_threads=timed_out_consumers,
                errors=_canonical_errors(errors),
            )
        if lifecycle_interruption is not None:
            _preserve_failed_bundle(bundle_writer, quarantine=device_axis_capture)
            raise lifecycle_interruption
        any_storage_fatal = any(outcome.storage_fatal for outcome in ordered_outcomes)
        any_data = any(outcome.captured_sample_count for outcome in ordered_outcomes)
        capture_failed = any(
            outcome.state is not StreamState.COMPLETE for outcome in ordered_outcomes
        )
        peer_failure_rejected = fail_whole and (
            any(
                outcome.state is StreamState.FAILED
                or not isinstance(outcome.receipt, DeviceAxisStreamWriteReceipt)
                for outcome in ordered_outcomes
            )
            if device_axis_capture
            else capture_failed
        )
        cancelled = external_cancel.is_set()
        if any_storage_fatal or not any_data or cancelled or peer_failure_rejected:
            _preserve_failed_bundle(bundle_writer, quarantine=device_axis_capture)
            if cancelled:
                errors.append("capture cancelled; no manifest was published")
            if peer_failure_rejected:
                errors.append("peer-failure policy rejected a partial paired capture")
            return CaptureSessionResult(
                session_id=session_id,
                state=CaptureState.FAILED,
                admission=admission,
                release_target_monotonic_ns=release_target,
                errors=_canonical_errors(errors),
                stream_coverage=tuple(
                    outcome.coverage for outcome in ordered_outcomes if outcome.coverage is not None
                ),
            )

        try:
            streams = tuple(_recording_stream(plan, outcome) for outcome in ordered_outcomes)
            state: Literal[CaptureState.COMMITTED, CaptureState.DEGRADED] = (
                CaptureState.COMMITTED
                if all(stream.state is StreamState.COMPLETE for stream in streams)
                else CaptureState.DEGRADED
            )
            synchronization = _synchronization_summary(plan, streams, release_target)
            finalized_utc_ns = max(created_utc_ns, self.clock.utc_ns())
            tags = tuple(sorted(_plan_tags(plan) | set(extra_tags)))
            if device_axis_capture:
                if not all(isinstance(stream, RecordingStreamV3) for stream in streams):
                    raise AcquisitionError("device-axis capture did not produce exact streams")
                if isinstance(plan, CapturePlanV5):
                    manifest: (
                        RecordingManifestV1
                        | RecordingManifestV3
                        | RecordingManifestV4
                        | RecordingManifestV5
                        | RecordingManifestV6
                    ) = RecordingManifestV6(
                        session_id=session_id,
                        state=state,
                        source_type=plan.source_type,
                        created_utc_ns=created_utc_ns,
                        finalized_utc_ns=finalized_utc_ns,
                        capture_plan=plan,
                        tags=tags,
                        streams=cast(tuple[RecordingStreamV3, RecordingStreamV3], streams),
                        synchronization=synchronization,
                        compression=compression,
                        host=self._host,
                        producer=self._producer,
                    )
                elif isinstance(plan, CapturePlanV4):
                    manifest = RecordingManifestV5(
                        session_id=session_id,
                        state=state,
                        source_type=plan.source_type,
                        created_utc_ns=created_utc_ns,
                        finalized_utc_ns=finalized_utc_ns,
                        capture_plan=plan,
                        tags=tags,
                        streams=cast(tuple[RecordingStreamV3, RecordingStreamV3], streams),
                        synchronization=synchronization,
                        compression=compression,
                        host=self._host,
                        producer=self._producer,
                    )
                elif isinstance(plan, CapturePlanV3):
                    manifest = RecordingManifestV4(
                        session_id=session_id,
                        state=state,
                        source_type=plan.source_type,
                        created_utc_ns=created_utc_ns,
                        finalized_utc_ns=finalized_utc_ns,
                        capture_plan=plan,
                        tags=tags,
                        streams=cast(tuple[RecordingStreamV3, RecordingStreamV3], streams),
                        synchronization=synchronization,
                        compression=compression,
                        host=self._host,
                        producer=self._producer,
                    )
                elif isinstance(plan, CapturePlanV2):
                    manifest = RecordingManifestV3(
                        session_id=session_id,
                        state=state,
                        source_type=plan.source_type,
                        created_utc_ns=created_utc_ns,
                        finalized_utc_ns=finalized_utc_ns,
                        capture_plan=plan,
                        tags=tags,
                        streams=cast(tuple[RecordingStreamV3, ...], streams),
                        synchronization=synchronization,
                        compression=compression,
                        host=self._host,
                        producer=self._producer,
                    )
                else:
                    raise AcquisitionError("device-axis capture requires CapturePlanV2 or V3")
            elif isinstance(plan, CapturePlanV2):
                if any(isinstance(stream, RecordingStreamV3) for stream in streams):
                    raise AcquisitionError("legacy V2 capture produced a V3 stream")
                manifest = RecordingManifestV2(
                    session_id=session_id,
                    state=state,
                    source_type=plan.source_type,
                    created_utc_ns=created_utc_ns,
                    finalized_utc_ns=finalized_utc_ns,
                    capture_plan=plan,
                    tags=tags,
                    streams=cast(tuple[RecordingStreamV2, ...], streams),
                    synchronization=synchronization,
                    compression=compression,
                    host=self._host,
                    producer=self._producer,
                )
            else:
                if isinstance(plan, (CapturePlanV3, CapturePlanV4, CapturePlanV5)):
                    raise AcquisitionError("mixed-rate plan requires device-axis storage")
                if any(isinstance(stream, RecordingStreamV3) for stream in streams):
                    raise AcquisitionError("legacy V1 capture produced a V3 stream")
                manifest = RecordingManifestV1(
                    session_id=session_id,
                    state=state,
                    source_type=plan.source_type,
                    created_utc_ns=created_utc_ns,
                    finalized_utc_ns=finalized_utc_ns,
                    capture_plan=plan,
                    tags=tags,
                    streams=cast(tuple[RecordingStreamV1, ...], streams),
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
                stream_coverage=tuple(
                    outcome.coverage for outcome in ordered_outcomes if outcome.coverage is not None
                ),
            )
        except BaseException as error:
            _preserve_failed_bundle(bundle_writer, quarantine=device_axis_capture)
            if not isinstance(error, Exception):
                raise
            errors.append(_error_text(error))
            return CaptureSessionResult(
                session_id=session_id,
                state=CaptureState.FAILED,
                admission=admission,
                release_target_monotonic_ns=release_target,
                errors=_canonical_errors(errors),
                stream_coverage=tuple(
                    outcome.coverage for outcome in ordered_outcomes if outcome.coverage is not None
                ),
            )

    def _compression_for(self, plan: CapturePlan) -> CompressionSettingsV1:
        policies = {
            _profile_for_radio(plan, radio_id).storage_policy for radio_id in plan.radio_ids
        }
        if len(policies) != 1:
            raise ValueError("mixed-rate capture profiles disagree on compression policy")
        policy_id = next(iter(policies))
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
        plan: CapturePlan,
        sources: Mapping[str, RadioSource],
    ) -> tuple[RadioSource, ...]:
        if plan.source_type is SourceType.LIVE and plan.schema_version not in {2, 3, 4, 5}:
            raise ValueError(
                "new live capture requires counter-authoritative CapturePlanV2, V3, V4, or V5"
            )
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
        plan: CapturePlan,
        sources: tuple[RadioSource, ...],
        requested_settings: Mapping[str, RadioSettingsV1],
        cancel: Event,
    ) -> tuple[dict[int, _PreparedRadio], dict[int, str], BaseException | None]:
        prepared: dict[int, _PreparedRadio] = {}
        failures: dict[int, str] = {}
        interruption: BaseException | None = None
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
                except BaseException as error:
                    failures[index] = (
                        f"{plan.radio_ids[index]} prepare failed: {_error_text(error)}"
                    )
                    if not isinstance(error, Exception) and interruption is None:
                        interruption = error
        return prepared, failures, interruption

    def _prepare_radio(
        self,
        index: int,
        source: RadioSource,
        expected_radio_id: str,
        requested_settings: RadioSettingsV1,
        plan: CapturePlan,
        cancel: Event,
    ) -> _PreparedRadio:
        try:
            identity = source.open()
            if identity.radio_id != expected_radio_id or source.identity != identity:
                raise AcquisitionError(
                    "opened radio identity does not match its attested plan slot"
                )
            capabilities = source.capabilities
            counter_authoritative = plan.schema_version in {2, 3, 4, 5}
            if counter_authoritative and not (
                capabilities.supports_device_sample_counter
                and capabilities.supports_continuity_sequence
            ):
                raise AcquisitionError(
                    "radio does not attest device counter and continuity sequence"
                )
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
            if counter_authoritative:
                source.reset_receive_buffer()
            profile = _profile_for_radio(plan, expected_radio_id)
            exact_rf_geometry = (
                isinstance(plan, (CapturePlanV3, CapturePlanV4, CapturePlanV5))
                or "NATIVE_BANDWIDTH" in profile.tags
            )
            configure_exact = getattr(source, "configure_exact", None)
            actual = (
                configure_exact(requested_settings)
                if exact_rf_geometry and callable(configure_exact)
                else source.configure(requested_settings)
            )
            _validate_settings_readback(
                requested_settings,
                actual,
                exact_rf_geometry=exact_rf_geometry,
            )
            self.clock.sleep(float(profile.settle_seconds), cancel)
            for _ in range(profile.prime_refills):
                if cancel.is_set():
                    raise AcquisitionCancelled("capture cancelled while priming")
                source.read_block(profile.refill_samples)
            if counter_authoritative:
                if not isinstance(
                    plan, (CapturePlanV2, CapturePlanV3, CapturePlanV4, CapturePlanV5)
                ):
                    raise AcquisitionError("counter-authoritative plan type is unsupported")
                if not isinstance(profile, CaptureProfileV2):
                    raise AcquisitionError("counter-authoritative profile type is unsupported")
                source.reset_receive_buffer()
            return _PreparedRadio(
                index,
                f"stream-{index}",
                source,
                identity,
                requested_settings,
                actual,
            )
        except BaseException as error:
            close_interruption: BaseException | None = None
            try:
                source.close()
            except BaseException as close_error:
                if not isinstance(close_error, Exception):
                    close_interruption = close_error
            if isinstance(error, Exception) and close_interruption is not None:
                raise close_interruption from error
            raise

    def _capture_radio(
        self,
        item: _PreparedRadio,
        plan: CapturePlan,
        bundle: RecordingBundleWriter,
        gate: _ReadinessGate,
        rf_drain_gate: _RfDrainGate,
        external_cancel: Event,
        session_cancel: Event,
        fail_whole: bool,
    ) -> _StreamOutcome:
        if plan.schema_version in {2, 3, 4, 5}:
            if not isinstance(plan, (CapturePlanV2, CapturePlanV3, CapturePlanV4, CapturePlanV5)):
                raise AcquisitionError("counter-authoritative plan type is unsupported")
            return self._capture_radio_v2(
                item,
                plan,
                bundle,
                gate,
                rf_drain_gate,
                external_cancel,
                session_cancel,
                fail_whole,
            )
        if not isinstance(plan, CapturePlanV1):
            raise AcquisitionError("legacy capture plan type is unsupported")
        receipt: StreamWriteReceipt | None = None
        stream_writer = None
        captured = 0
        first_metadata: IqBlockMetadataV1 | None = None
        last_metadata: IqBlockMetadataV1 | None = None
        release_observed: int | None = None
        release_target: int | None = None
        error_text: str | None = None
        storage_fatal = False
        interruption: BaseException | None = None
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
        except BaseException as error:
            error_text = _error_text(error)
            if not isinstance(error, Exception):
                interruption = error
            if fail_whole:
                session_cancel.set()
        finally:
            if stream_writer is not None:
                try:
                    receipt = stream_writer.finalize()
                except BaseException as error:
                    storage_fatal = True
                    error_text = f"storage finalization failed: {_error_text(error)}"
                    if not isinstance(error, Exception) and interruption is None:
                        interruption = error
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
            interruption=interruption,
            coverage=project_capture_progress_coverage(
                radio_id=item.identity.radio_id,
                stream_id=item.stream_id,
                requested_samples=plan.resolved_sample_count,
                observed_samples=captured,
                covered_device_samples=captured,
            ),
        )

    def _capture_radio_v2(
        self,
        item: _PreparedRadio,
        plan: CapturePlanV2 | CapturePlanV3 | CapturePlanV4 | CapturePlanV5,
        bundle: RecordingBundleWriter,
        gate: _ReadinessGate,
        rf_drain_gate: _RfDrainGate,
        external_cancel: Event,
        session_cancel: Event,
        fail_whole: bool,
    ) -> _StreamOutcome:
        """Drain RF without waiting for compression; duration follows the device axis."""

        profile, resolved_sample_count, _settings = _radio_geometry(plan, item.identity.radio_id)
        if not isinstance(profile, CaptureProfileV2):
            raise AcquisitionError("counter-authoritative capture requires CaptureProfileV2")
        device_axis_capture = profile.storage_policy == DEVICE_AXIS_STORAGE_POLICY_V1
        device_buffer = _device_buffer_request(profile, resolved_sample_count)
        ring_evidence: DeviceBufferEvidenceV1 | None = None
        direct_evidence: DirectAsyncEvidence | None = None
        kernel_buffers: int | None = None
        pending: queue.Queue[IqBlock | object] = queue.Queue(maxsize=profile.refill_queue_capacity)
        stop = object()
        consumer_failed = Event()
        consumer_error: list[str] = []
        receipt_holder: list[StreamWriteReceipt | DeviceAxisStreamWriteReceipt] = []
        queue_depth_lock = threading.Lock()
        consumer_phase_lock = threading.Lock()
        queue_slots = threading.BoundedSemaphore(profile.refill_queue_capacity)
        queued_refills = 0
        queue_high_water = 0
        enqueue_failures = 0
        maximum_service_ns = 0
        terminal_gap_metadata: IqBlockMetadataV2 | None = None
        terminal_enqueue_failure_metadata: IqBlockMetadataV2 | None = None
        consumer_phase: Literal[
            "starting", "waiting", "writing", "finalizing", "aborting", "stopped"
        ] = "starting"

        def set_consumer_phase(
            phase: Literal["starting", "waiting", "writing", "finalizing", "aborting", "stopped"],
        ) -> None:
            nonlocal consumer_phase
            with consumer_phase_lock:
                consumer_phase = phase

        def observed_consumer_phase() -> str:
            with consumer_phase_lock:
                return consumer_phase

        def consume() -> None:
            nonlocal queued_refills
            stream_writer: StreamBundleWriter | DeviceAxisStreamBundleWriter | None = None
            raw_stage: RawIqStage | None = None

            def open_writer() -> StreamBundleWriter | DeviceAxisStreamBundleWriter:
                if kernel_buffers is None:
                    raise AcquisitionError("verified kernel-buffer readback is unavailable")
                if device_axis_capture:
                    return bundle.open_device_axis_stream(
                        item.stream_id,
                        item.identity,
                        item.applied_settings.receiver_ids,
                        requested_device_span=resolved_sample_count,
                        kernel_buffers=kernel_buffers,
                        allow_non_refill_gaps=isinstance(
                            device_buffer,
                            (
                                DirectAsyncRequestV1,
                                DirectAsyncRamDropRequestV2,
                                DirectAsyncRamDropRequestV3,
                            ),
                        ),
                    )
                return bundle.open_stream(
                    item.stream_id,
                    item.identity,
                    item.applied_settings.receiver_ids,
                    counter_authoritative=True,
                    kernel_buffers=kernel_buffers,
                )

            try:
                while True:
                    set_consumer_phase("waiting")
                    queued = pending.get()
                    try:
                        if queued is not stop:
                            with queue_depth_lock:
                                if queued_refills <= 0:
                                    raise AcquisitionError("refill queue accounting underflowed")
                                queued_refills -= 1
                                queue_slots.release()
                        if queued is stop:
                            break
                        if consumer_failed.is_set():
                            continue
                        assert isinstance(queued, IqBlock)
                        set_consumer_phase("writing")
                        if device_axis_capture:
                            if raw_stage is None:
                                raw_stage = bundle.open_raw_stage(
                                    item.stream_id,
                                    maximum_bytes=resolved_sample_count
                                    * len(profile.receivers)
                                    * 4,
                                )
                            raw_stage.append(queued)
                        else:
                            if stream_writer is None:
                                stream_writer = open_writer()
                            stream_writer.append(queued)
                    except Exception as error:
                        consumer_error.append(_error_text(error))
                        consumer_failed.set()
                    finally:
                        pending.task_done()
                if raw_stage is not None and not consumer_failed.is_set():
                    rf_drain_gate.wait_until_drained()
                    raw_stage.seal()
                    buffer_evidence = ring_evidence or direct_evidence
                    if device_buffer is not None and buffer_evidence is None:
                        # The producer retains the original RF/cancellation error;
                        # keep the raw spool without fabricating a publishable tail.
                        return
                    set_consumer_phase("finalizing")
                    stream_writer = open_writer()
                    for index, staged in enumerate(raw_stage.blocks()):
                        if index == 0 and buffer_evidence is not None:
                            metadata = staged.metadata.model_copy(
                                update={
                                    "hardware_metadata": {
                                        **staged.metadata.hardware_metadata,
                                        (
                                            DDR_RING_EVIDENCE_KEY_V1
                                            if ring_evidence is not None
                                            else (
                                                DIRECT_ASYNC_RAM_DROP_EVIDENCE_KEY_V3
                                                if isinstance(
                                                    direct_evidence,
                                                    DirectAsyncRamDropEvidenceV3,
                                                )
                                                else (
                                                    DIRECT_ASYNC_RAM_DROP_EVIDENCE_KEY_V2
                                                    if isinstance(
                                                        direct_evidence,
                                                        DirectAsyncRamDropEvidenceV2,
                                                    )
                                                    else DIRECT_ASYNC_EVIDENCE_KEY_V1
                                                )
                                            )
                                        ): buffer_evidence.model_dump(mode="json"),
                                    }
                                }
                            )
                            staged = IqBlock(samples=staged.samples, metadata=metadata)
                        stream_writer.append(staged)
                if stream_writer is not None and not consumer_failed.is_set():
                    set_consumer_phase("finalizing")
                    queue_telemetry = StreamQueueTelemetry(
                        capacity_refills=profile.refill_queue_capacity,
                        high_water_refills=queue_high_water,
                        enqueue_failure_count=enqueue_failures,
                        maximum_refill_service_interval_ns=maximum_service_ns,
                    )
                    if isinstance(stream_writer, DeviceAxisStreamBundleWriter):
                        receipt_holder.append(
                            stream_writer.finalize(
                                queue_telemetry=queue_telemetry,
                                terminal_gap_metadata=terminal_gap_metadata,
                                terminal_enqueue_failure_metadata=(
                                    terminal_enqueue_failure_metadata
                                ),
                            )
                        )
                    else:
                        receipt_holder.append(
                            stream_writer.finalize(
                                queue_telemetry=queue_telemetry,
                                terminal_gap_metadata=terminal_gap_metadata,
                                terminal_enqueue_failure_metadata=(
                                    terminal_enqueue_failure_metadata
                                ),
                                requested_device_span=resolved_sample_count,
                            )
                        )
                    if raw_stage is not None:
                        raw_stage.discard_after_finalize()
                elif stream_writer is not None:
                    set_consumer_phase("aborting")
                    stream_writer.abort()
            except BaseException as error:
                consumer_error.append(_error_text(error))
                consumer_failed.set()
            finally:
                if raw_stage is not None:
                    raw_stage.close()
                set_consumer_phase("stopped")

        consumer = threading.Thread(
            target=consume,
            name=f"leo-store-{item.stream_id}",
            daemon=True,
        )
        consumer.start()
        captured = 0
        returned_frames = 0
        returned_samples = 0
        returned_device_span = 0
        prefix_contiguous = True
        device_span = 0
        first_counter: int | None = None
        first_metadata: IqBlockMetadataV1 | None = None
        last_metadata: IqBlockMetadataV1 | None = None
        release_observed: int | None = None
        release_target: int | None = None
        error_text: str | None = None
        consumer_timed_out = False
        interruption: BaseException | None = None
        direct_segment_pending = isinstance(
            device_buffer,
            (DirectAsyncRequestV1, DirectAsyncRamDropRequestV2, DirectAsyncRamDropRequestV3),
        )
        direct_upstream_generations: list[str] = []
        direct_logical_generation: str | None = None
        direct_previous_counter: int | None = None
        direct_logical_sequence: int | None = None
        direct_missing_samples = 0
        direct_inter_segment_skipped_samples = 0
        validator = ContinuityChainValidator(
            require_metadata=True,
            require_generation=True,
            validate_declared=True,
            allow_non_refill_gaps=isinstance(
                device_buffer,
                (DirectAsyncRequestV1, DirectAsyncRamDropRequestV2, DirectAsyncRamDropRequestV3),
            ),
        )
        try:
            release_target = gate.arrive_and_wait(external_cancel)
            release_observed = self.clock.wait_until(release_target, external_cancel)
            arm_started = self.clock.monotonic_ns()
            controller = _gain_controller_for_radio(plan, item.identity.radio_id)
            try:
                if isinstance(
                    device_buffer,
                    (
                        DirectAsyncRequestV1,
                        DirectAsyncRamDropRequestV2,
                        DirectAsyncRamDropRequestV3,
                    ),
                ):
                    kernel_buffers = item.source.begin_metadata_capture(
                        profile.refill_samples,
                        kernel_buffers=profile.kernel_buffers,
                        gain_controller=controller,
                        device_buffer=device_buffer,
                        direct_async_frames=device_buffer.next_segment_frames(0),
                    )
                elif device_buffer is not None:
                    kernel_buffers = item.source.begin_metadata_capture(
                        profile.refill_samples,
                        kernel_buffers=profile.kernel_buffers,
                        gain_controller=controller,
                        device_buffer=device_buffer,
                    )
                elif controller is None:
                    kernel_buffers = item.source.begin_metadata_capture(
                        profile.refill_samples,
                        kernel_buffers=profile.kernel_buffers,
                    )
                else:
                    kernel_buffers = item.source.begin_metadata_capture(
                        profile.refill_samples,
                        kernel_buffers=profile.kernel_buffers,
                        gain_controller=controller,
                    )
            except BaseException:
                arm_completed = self.clock.monotonic_ns()
                _LOG.error(
                    "metadata_capture_arm_failed radio=%s stream=%s "
                    "release_target_monotonic_ns=%d release_observed_monotonic_ns=%d "
                    "arm_started_monotonic_ns=%d arm_completed_monotonic_ns=%d "
                    "arm_duration_ns=%d",
                    item.identity.radio_id,
                    item.stream_id,
                    release_target,
                    release_observed,
                    arm_started,
                    arm_completed,
                    arm_completed - arm_started,
                )
                raise
            arm_completed = self.clock.monotonic_ns()
            if kernel_buffers != profile.kernel_buffers:
                raise AcquisitionError(
                    "radio kernel-buffer readback disagrees with CaptureProfileV2"
                )
            _LOG.info(
                "metadata_capture_armed radio=%s stream=%s "
                "release_target_monotonic_ns=%d release_observed_monotonic_ns=%d "
                "arm_started_monotonic_ns=%d arm_completed_monotonic_ns=%d "
                "arm_duration_ns=%d kernel_buffers=%d",
                item.identity.radio_id,
                item.stream_id,
                release_target,
                release_observed,
                arm_started,
                arm_completed,
                arm_completed - arm_started,
                kernel_buffers,
            )
            while (
                returned_frames < device_buffer.target_frames
                if device_buffer is not None
                else device_span < resolved_sample_count
            ):
                if external_cancel.is_set() or (fail_whole and session_cancel.is_set()):
                    raise AcquisitionCancelled("capture cancelled at a refill boundary")
                if consumer_failed.is_set():
                    raise AcquisitionError(f"storage consumer failed: {consumer_error[-1]}")
                if (
                    isinstance(
                        device_buffer,
                        (
                            DirectAsyncRequestV1,
                            DirectAsyncRamDropRequestV2,
                            DirectAsyncRamDropRequestV3,
                        ),
                    )
                    and returned_frames
                    and returned_frames % device_buffer.maximum_segment_frames == 0
                ):
                    item.source.reset_receive_buffer()
                    segment_kernel_buffers = item.source.begin_metadata_capture(
                        profile.refill_samples,
                        kernel_buffers=profile.kernel_buffers,
                        gain_controller=controller,
                        device_buffer=device_buffer,
                        direct_async_frames=device_buffer.next_segment_frames(returned_frames),
                    )
                    if segment_kernel_buffers != kernel_buffers:
                        raise AcquisitionError(
                            "direct-async segment changed the kernel-buffer readback"
                        )
                    direct_segment_pending = True
                count = (
                    profile.refill_samples
                    if device_buffer is not None
                    else min(profile.refill_samples, resolved_sample_count - device_span)
                )
                block = item.source.read_block(count)
                block = _validate_and_rebase_block(
                    block,
                    item,
                    count,
                    returned_samples if device_buffer is not None else captured,
                )
                if isinstance(
                    device_buffer,
                    (
                        DirectAsyncRequestV1,
                        DirectAsyncRamDropRequestV2,
                        DirectAsyncRamDropRequestV3,
                    ),
                ):
                    raw_metadata = block.metadata
                    if not isinstance(raw_metadata, IqBlockMetadataV2):
                        raise AcquisitionError("direct-async capture returned legacy metadata")
                    if raw_metadata.device_sample_counter is None:
                        raise AcquisitionError("direct-async metadata omits the device counter")
                    raw_generation = raw_metadata.stream_generation
                    if direct_segment_pending:
                        if raw_generation in direct_upstream_generations:
                            raise AcquisitionError(
                                "direct-async segment reused an upstream stream generation"
                            )
                        direct_upstream_generations.append(raw_generation)
                        direct_segment_pending = False
                    if first_counter is None:
                        direct_logical_generation = raw_generation
                        normalized_sequence = 0
                    else:
                        assert direct_previous_counter is not None
                        assert direct_logical_sequence is not None
                        missing = raw_metadata.device_sample_counter - (
                            direct_previous_counter + profile.refill_samples
                        )
                        if missing < 0:
                            raise AcquisitionError(
                                "direct-async device counter regressed or overlapped"
                            )
                        skipped_refills = (
                            missing // profile.refill_samples
                            if missing % profile.refill_samples == 0
                            else 0
                        )
                        normalized_sequence = direct_logical_sequence + 1 + skipped_refills
                    direct_previous_counter = raw_metadata.device_sample_counter
                    direct_logical_sequence = normalized_sequence
                    assert direct_logical_generation is not None
                    block = IqBlock(
                        samples=block.samples,
                        metadata=type(raw_metadata).model_validate(
                            {
                                **raw_metadata.model_dump(mode="json"),
                                "stream_generation": direct_logical_generation,
                                "source_sequence": normalized_sequence,
                                "continuity": ContinuityStatus.UNKNOWN.value,
                                "missing_samples_before": 0,
                                "hardware_metadata": {
                                    **raw_metadata.hardware_metadata,
                                    "direct_async_upstream_stream_generation": raw_generation,
                                    "direct_async_upstream_source_sequence": (
                                        raw_metadata.source_sequence
                                    ),
                                    "direct_async_segment_index": (
                                        len(direct_upstream_generations) - 1
                                    ),
                                },
                            }
                        ),
                    )
                metadata = validator.observe(block.metadata)
                if not isinstance(metadata, IqBlockMetadataV2):
                    raise AcquisitionError("V2 capture returned legacy IQ metadata")
                block = IqBlock(samples=block.samples, metadata=metadata)
                refill_metadata = metadata
                assert metadata.device_sample_counter is not None
                if first_counter is None:
                    first_counter = metadata.device_sample_counter
                block_device_start = metadata.device_sample_counter - first_counter
                returned_frames += 1
                returned_samples += count
                returned_device_span = block_device_start + count
                if isinstance(device_buffer, DeviceBufferRequestV1) and returned_frames <= min(
                    device_buffer.capacity_frames, device_buffer.target_frames
                ):
                    prefix_contiguous = prefix_contiguous and (
                        block_device_start == (returned_frames - 1) * count
                        and not metadata.overflow_observed
                    )
                    if not prefix_contiguous:
                        raise AcquisitionError("DDR ring protected prefix is not contiguous")
                if isinstance(
                    device_buffer,
                    (
                        DirectAsyncRequestV1,
                        DirectAsyncRamDropRequestV2,
                        DirectAsyncRamDropRequestV3,
                    ),
                ):
                    direct_missing_samples += metadata.missing_samples_before
                    if len(direct_upstream_generations) > 1 and (
                        raw_generation == direct_upstream_generations[-1]
                        and raw_metadata.source_sequence == 0
                    ):
                        direct_inter_segment_skipped_samples += metadata.missing_samples_before
                # A finite firmware target counts delivered frames, not device time.
                # Drain its bounded tail, but never extend the published dwell window.
                if device_span == resolved_sample_count:
                    continue
                accepted_count = min(
                    metadata.sample_count,
                    max(0, resolved_sample_count - block_device_start),
                )
                service_ns = (
                    metadata.host_request_monotonic_ns.upper_ns
                    - metadata.host_request_monotonic_ns.lower_ns
                )
                maximum_service_ns = max(maximum_service_ns, service_ns)
                if accepted_count == 0:
                    if metadata.continuity is not ContinuityStatus.GAP_BEFORE:
                        raise AcquisitionError(
                            "refill begins beyond requested device span without a gap"
                        )
                    terminal_gap_metadata = metadata
                    device_span = resolved_sample_count
                    _log_gap(item, metadata)
                    if device_buffer is None:
                        break
                    continue
                if accepted_count < metadata.sample_count:
                    block = _truncate_iq_block(
                        block,
                        accepted_count,
                        item.applied_settings.sample_rate_hz,
                    )
                    metadata = block.metadata
                    assert isinstance(metadata, IqBlockMetadataV2)
                new_device_span = block_device_start + accepted_count
                slot_acquired = queue_slots.acquire(blocking=False)
                try:
                    if not slot_acquired:
                        raise queue.Full
                    with queue_depth_lock:
                        pending.put_nowait(block)
                        queued_refills += 1
                        queue_high_water = max(queue_high_water, queued_refills)
                except queue.Full as error:
                    if slot_acquired:
                        queue_slots.release()
                    enqueue_failures += 1
                    # Preserve the exact validated refill header, not a logical
                    # prefix metadata object produced when the refill overlaps
                    # the requested device-span endpoint.
                    terminal_enqueue_failure_metadata = refill_metadata
                    if refill_metadata.continuity is ContinuityStatus.GAP_BEFORE:
                        _log_gap(item, refill_metadata)
                    if refill_metadata.overflow_observed:
                        _LOG.error(
                            "radio=%s stream=%s terminal_rejected_overflow=true",
                            item.identity.radio_id,
                            refill_metadata.stream_generation,
                        )
                    _LOG.error(
                        "radio=%s stream=%s refill_queue_full=true "
                        "rejected_counter=%d rejected_missing_samples=%d",
                        item.identity.radio_id,
                        refill_metadata.stream_generation,
                        refill_metadata.device_sample_counter,
                        refill_metadata.missing_samples_before,
                    )
                    raise AcquisitionError(
                        "refill queue full; capture cannot drain RF without blocking"
                    ) from error
                if first_metadata is None:
                    first_metadata = metadata
                last_metadata = metadata
                captured += accepted_count
                device_span = new_device_span
                if metadata.continuity is ContinuityStatus.GAP_BEFORE:
                    _log_gap(item, metadata)
                    if profile.continuity_policy is ContinuityPolicy.REQUIRE_CONTIGUOUS:
                        raise AcquisitionError(
                            "continuity policy stopped capture after persisting a counter gap"
                        )
                elif metadata.continuity is ContinuityStatus.OVERFLOW:
                    _LOG.error(
                        "radio=%s stream=%s overflow flag without counter gap",
                        item.identity.radio_id,
                        metadata.stream_generation,
                    )
            if isinstance(device_buffer, DeviceBufferRequestV1):
                status = item.source.ddr_ring_status()
                if not isinstance(status, DdrRingStatusV1):
                    raise AcquisitionError("DDR ring status has the wrong contract generation")
                prefix_frames = min(device_buffer.capacity_frames, device_buffer.target_frames)
                assert first_counter is not None
                prefix_end = first_counter + prefix_frames * profile.refill_samples
                if (
                    status.high_water_frames < prefix_frames
                    or status.last_contiguous_sample_sequence is None
                    or status.last_contiguous_sample_sequence < prefix_end
                    or (
                        status.first_unavailable_sample_sequence is not None
                        and status.first_unavailable_sample_sequence < prefix_end
                    )
                ):
                    raise AcquisitionError("DDR ring status does not attest the protected prefix")
                ring_evidence = DeviceBufferEvidenceV1(
                    request=device_buffer,
                    status=status,
                    returned_frames=returned_frames,
                    returned_device_span_samples=returned_device_span,
                    protected_prefix_frames=prefix_frames,
                    protected_prefix_bytes=prefix_frames * profile.refill_samples * 4,
                    stored_observed_samples=captured,
                    drained_outside_window_samples=returned_samples - captured,
                )
                item.source.reset_receive_buffer()
                _LOG.info(
                    "ddr_ring_complete radio=%s stream=%s frames=%d bytes=%d "
                    "stored_samples=%d drained_outside_window_samples=%d wraps=%d",
                    item.identity.radio_id,
                    item.stream_id,
                    returned_frames,
                    status.admitted_capacity_iq_bytes,
                    captured,
                    returned_samples - captured,
                    status.wrap_count,
                )
            elif isinstance(
                device_buffer,
                (DirectAsyncRequestV1, DirectAsyncRamDropRequestV2, DirectAsyncRamDropRequestV3),
            ):
                if isinstance(
                    device_buffer, (DirectAsyncRamDropRequestV2, DirectAsyncRamDropRequestV3)
                ):
                    status = item.source.ddr_ring_status()
                    if not isinstance(status, DirectAsyncRamStatusV2):
                        raise AcquisitionError(
                            "direct-async RAM/drop status has the wrong contract generation"
                        )
                    if isinstance(device_buffer, DirectAsyncRamDropRequestV3):
                        direct_evidence = DirectAsyncRamDropEvidenceV3(
                            request=device_buffer,
                            status=status,
                            returned_frames=returned_frames,
                            returned_device_span_samples=returned_device_span,
                            segment_count=len(direct_upstream_generations),
                            upstream_stream_generations=tuple(direct_upstream_generations),
                            counter_missing_sample_count=direct_missing_samples,
                            inter_segment_skipped_samples=direct_inter_segment_skipped_samples,
                            stored_observed_samples=captured,
                            drained_outside_window_samples=returned_samples - captured,
                        )
                    else:
                        direct_evidence = DirectAsyncRamDropEvidenceV2(
                            request=device_buffer,
                            status=status,
                            returned_frames=returned_frames,
                            returned_device_span_samples=returned_device_span,
                            segment_count=len(direct_upstream_generations),
                            upstream_stream_generations=tuple(direct_upstream_generations),
                            counter_missing_sample_count=direct_missing_samples,
                            inter_segment_skipped_samples=direct_inter_segment_skipped_samples,
                            stored_observed_samples=captured,
                            drained_outside_window_samples=returned_samples - captured,
                        )
                else:
                    direct_evidence = DirectAsyncEvidenceV1(
                        request=device_buffer,
                        returned_frames=returned_frames,
                        returned_device_span_samples=returned_device_span,
                        segment_count=len(direct_upstream_generations),
                        upstream_stream_generations=tuple(direct_upstream_generations),
                        counter_missing_sample_count=direct_missing_samples,
                        inter_segment_skipped_samples=direct_inter_segment_skipped_samples,
                        stored_observed_samples=captured,
                        drained_outside_window_samples=returned_samples - captured,
                    )
                item.source.reset_receive_buffer()
                _LOG.info(
                    "direct_async_complete radio=%s stream=%s frames=%d segments=%d "
                    "stored_samples=%d drained_outside_window_samples=%d "
                    "missing_samples=%d inter_segment_skipped_samples=%d "
                    "ram_spilled_frames=%d ram_drained_frames=%d ram_dropped_frames=%d",
                    item.identity.radio_id,
                    item.stream_id,
                    returned_frames,
                    direct_evidence.segment_count,
                    captured,
                    returned_samples - captured,
                    direct_missing_samples,
                    direct_inter_segment_skipped_samples,
                    (
                        direct_evidence.ram_spilled_frames
                        if isinstance(
                            direct_evidence,
                            (DirectAsyncRamDropEvidenceV2, DirectAsyncRamDropEvidenceV3),
                        )
                        else 0
                    ),
                    (
                        direct_evidence.ram_drained_frames
                        if isinstance(
                            direct_evidence,
                            (DirectAsyncRamDropEvidenceV2, DirectAsyncRamDropEvidenceV3),
                        )
                        else 0
                    ),
                    (
                        direct_evidence.ram_dropped_frames
                        if isinstance(
                            direct_evidence,
                            (DirectAsyncRamDropEvidenceV2, DirectAsyncRamDropEvidenceV3),
                        )
                        else 0
                    ),
                )
        except BaseException as error:
            error_text = _error_text(error)
            if device_buffer is not None:
                failure_coverage = project_capture_progress_coverage(
                    radio_id=item.identity.radio_id,
                    stream_id=item.stream_id,
                    requested_samples=resolved_sample_count,
                    observed_samples=captured,
                    covered_device_samples=device_span,
                    direct_async_request=(
                        device_buffer
                        if isinstance(
                            device_buffer,
                            (
                                DirectAsyncRequestV1,
                                DirectAsyncRamDropRequestV2,
                                DirectAsyncRamDropRequestV3,
                            ),
                        )
                        else None
                    ),
                    returned_frames=returned_frames,
                    counter_missing_samples=direct_missing_samples,
                    inter_segment_skipped_samples=direct_inter_segment_skipped_samples,
                )
                diagnostic: dict[str, object] = {
                    "schema_version": 1,
                    "request": device_buffer.model_dump(mode="json"),
                    "returned_frames": returned_frames,
                    "returned_device_span_samples": returned_device_span,
                    "stored_observed_samples": captured,
                    "coverage": {
                        "delivery_unit": failure_coverage.delivery_unit,
                        "delivered_units": failure_coverage.delivered_units,
                        "requested_units": failure_coverage.requested_units,
                        "observed_samples": failure_coverage.observed_samples,
                        "logical_samples": failure_coverage.logical_samples,
                    },
                    "error": error_text,
                }
                if isinstance(device_buffer, DeviceBufferRequestV1):
                    try:
                        diagnostic["status"] = item.source.ddr_ring_status().model_dump(mode="json")
                    except Exception as status_error:
                        diagnostic["status_error"] = _error_text(status_error)
                else:
                    diagnostic.update(
                        {
                            "upstream_stream_generations": direct_upstream_generations,
                            "counter_missing_sample_count": direct_missing_samples,
                            "inter_segment_skipped_samples": (direct_inter_segment_skipped_samples),
                        }
                    )
                try:
                    bundle.write_capture_failure_evidence(
                        item.stream_id, canonical_json_bytes(diagnostic)
                    )
                except Exception:
                    _LOG.exception("could not persist DDR ring failure evidence")
            if not isinstance(error, Exception):
                interruption = error
            if fail_whole:
                session_cancel.set()
        finally:
            rf_drain_gate.arrive()
            shutdown_timeout = (
                self.config.raw_stage_finalize_timeout_seconds
                if device_axis_capture
                else self.config.consumer_shutdown_timeout_seconds
            )
            deadline = time.monotonic() + shutdown_timeout
            stop_enqueued = False
            while consumer.is_alive() and not stop_enqueued:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                try:
                    pending.put(stop, timeout=min(remaining, 0.05))
                    stop_enqueued = True
                except queue.Full:
                    continue
            consumer.join(timeout=max(0.0, deadline - time.monotonic()))
            if consumer.is_alive():
                consumer_timed_out = True
                bundle.quarantine()
                consumer_error.append("storage consumer did not stop before bounded timeout")
                consumer_failed.set()
                with queue_depth_lock:
                    remaining_refills = queued_refills
                _LOG.critical(
                    "storage_consumer_shutdown_timeout session=%s radio=%s stream=%s "
                    "timeout_seconds=%.3f phase=%s queued_refills=%d stop_enqueued=%s "
                    "live_supervisor_poisoned=%s",
                    bundle.session_id,
                    item.identity.radio_id,
                    item.stream_id,
                    shutdown_timeout,
                    observed_consumer_phase(),
                    remaining_refills,
                    str(stop_enqueued).lower(),
                    str(plan.source_type is SourceType.LIVE).lower(),
                )
            elif not stop_enqueued and not consumer_error:
                consumer_error.append("storage consumer exited before shutdown sentinel")
                consumer_failed.set()

        if consumer_error:
            error_text = f"storage consumer failed: {consumer_error[-1]}"
        receipt = receipt_holder[0] if receipt_holder else None
        storage_fatal = bool(consumer_error) or (captured > 0 and receipt is None)
        if receipt is not None:
            continuity = receipt.continuity
            assert isinstance(continuity, ContinuitySummaryV2)
            if error_text is None and (
                continuity.gap_count
                or continuity.overflow_count
                or continuity.enqueue_failure_count
                or continuity.device_span_sample_count != resolved_sample_count
            ):
                error_text = (
                    "capture integrity degraded: "
                    f"gaps={continuity.gap_count}, "
                    f"missing_samples={continuity.missing_sample_count}, "
                    f"overflows={continuity.overflow_count}, "
                    f"enqueue_failures={continuity.enqueue_failure_count}, "
                    f"device_span={continuity.device_span_sample_count}/"
                    f"{resolved_sample_count}"
                )
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
                device_axis_sample_count=(resolved_sample_count if device_axis_capture else None),
            )
        complete = (
            error_text is None
            and receipt is not None
            and captured == resolved_sample_count
            and device_span == resolved_sample_count
        )
        state = (
            StreamState.COMPLETE
            if complete
            else (StreamState.PARTIAL if captured and receipt is not None else StreamState.FAILED)
        )
        observed_samples = (
            receipt.observed_sample_count
            if isinstance(receipt, DeviceAxisStreamWriteReceipt)
            else (receipt.captured_sample_count if receipt is not None else captured)
        )
        covered_device_samples = (
            receipt.continuity.device_span_sample_count
            if isinstance(receipt, DeviceAxisStreamWriteReceipt)
            else device_span
        )
        return _StreamOutcome(
            index=item.index,
            stream_id=item.stream_id,
            identity=item.identity,
            requested_settings=item.requested_settings,
            applied_settings=item.applied_settings,
            state=state,
            captured_sample_count=(observed_samples if receipt is not None else 0),
            receipt=receipt,
            timing=timing if receipt is not None else None,
            error=error_text or (None if complete else "capture produced no publishable IQ"),
            storage_fatal=storage_fatal,
            timed_out_consumer=consumer if consumer_timed_out else None,
            interruption=interruption,
            coverage=project_capture_progress_coverage(
                radio_id=item.identity.radio_id,
                stream_id=item.stream_id,
                requested_samples=resolved_sample_count,
                observed_samples=observed_samples,
                covered_device_samples=covered_device_samples,
                direct_async_request=(
                    device_buffer
                    if isinstance(
                        device_buffer,
                        (
                            DirectAsyncRequestV1,
                            DirectAsyncRamDropRequestV2,
                            DirectAsyncRamDropRequestV3,
                        ),
                    )
                    else None
                ),
                returned_frames=returned_frames,
                counter_missing_samples=direct_missing_samples,
                inter_segment_skipped_samples=direct_inter_segment_skipped_samples,
            ),
        )

    def _publish_or_recover(
        self,
        writer: RecordingBundleWriter,
        manifest: (
            RecordingManifestV1
            | RecordingManifestV3
            | RecordingManifestV4
            | RecordingManifestV5
            | RecordingManifestV6
        ),
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


def _preserve_failed_bundle(
    writer: RecordingBundleWriter,
    *,
    quarantine: bool,
) -> None:
    """Close partial writers before permanently fencing V3 publication."""

    try:
        writer.close()
    finally:
        if quarantine and not writer.quarantined:
            writer.quarantine()


def _settings_from_profile(profile: CaptureProfileV1 | CaptureProfileV2) -> RadioSettingsV1:
    return RadioSettingsV1(
        center_frequency_hz=profile.center_frequency_hz,
        sample_rate_hz=profile.sample_rate_hz,
        bandwidth_hz=profile.bandwidth_hz,
        receiver_ids=profile.receivers,
        gain_mode=profile.gain_mode,
        gains=profile.gains,
    )


def _requested_settings_by_radio(
    plan: CapturePlan,
    overrides: Mapping[str, RadioSettingsV1] | None,
) -> dict[str, RadioSettingsV1]:
    if isinstance(plan, (CapturePlanV3, CapturePlanV4, CapturePlanV5)):
        planned = {item.radio_id: item.requested_settings for item in plan.radio_plans}
        if overrides is not None and dict(overrides) != planned:
            raise ValueError("mixed-rate per-radio settings are immutable plan authority")
        return planned
    default = _settings_from_profile(plan.profile_revision.profile)
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


def _profile_for_radio(plan: CapturePlan, radio_id: str) -> CaptureProfileV1 | CaptureProfileV2:
    if isinstance(plan, (CapturePlanV3, CapturePlanV4, CapturePlanV5)):
        matches = tuple(
            item.profile_revision.profile for item in plan.radio_plans if item.radio_id == radio_id
        )
        if len(matches) != 1:
            raise ValueError(f"mixed-rate plan has no unique radio geometry for {radio_id!r}")
        return matches[0]
    if radio_id not in plan.radio_ids:
        raise ValueError(f"capture plan has no radio {radio_id!r}")
    return plan.profile_revision.profile


def _radio_geometry(
    plan: CapturePlan,
    radio_id: str,
) -> tuple[CaptureProfileV1 | CaptureProfileV2, int, RadioSettingsV1]:
    profile = _profile_for_radio(plan, radio_id)
    if isinstance(plan, (CapturePlanV3, CapturePlanV4, CapturePlanV5)):
        leg = next(item for item in plan.radio_plans if item.radio_id == radio_id)
        return profile, leg.resolved_sample_count, leg.requested_settings
    return profile, plan.resolved_sample_count, _settings_from_profile(profile)


def _peer_failure_policy(plan: CapturePlan) -> PeerFailurePolicy:
    policies = {
        _profile_for_radio(plan, radio_id).peer_failure_policy for radio_id in plan.radio_ids
    }
    if len(policies) != 1:
        raise ValueError("capture plan profiles disagree on peer-failure policy")
    return next(iter(policies))


def _device_axis_capture(plan: CapturePlan) -> bool:
    policies = {_profile_for_radio(plan, radio_id).storage_policy for radio_id in plan.radio_ids}
    if len(policies) != 1:
        raise ValueError("capture plan profiles disagree on storage policy")
    return next(iter(policies)) == DEVICE_AXIS_STORAGE_POLICY_V1


def _gain_controller_for_radio(plan: CapturePlan, radio_id: str):
    if not isinstance(plan, (CapturePlanV4, CapturePlanV5)):
        return None
    matches = tuple(item.gain_controller for item in plan.radio_plans if item.radio_id == radio_id)
    if len(matches) != 1:
        raise ValueError(f"production plan has no unique gain controller for {radio_id!r}")
    return matches[0]


def _plan_tags(plan: CapturePlan) -> set[str]:
    tags = {tag for radio_id in plan.radio_ids for tag in _profile_for_radio(plan, radio_id).tags}
    if isinstance(plan, CapturePlanV3):
        tags.update(
            {
                "MIXED_RATE",
                f"mixed_rate_class:{plan.dwell_class.value}",
                f"tuning_policy:same:{plan.starlink_channel}:{plan.starlink_edge.value}",
            }
        )
    elif isinstance(plan, CapturePlanV4):
        tags.update(
            {
                "PRODUCTION_NATIVE_RATES_V2",
                f"production_dwell_class:{plan.dwell_class.value}",
                f"tuning_policy:{plan.tuning_branch.value}",
            }
        )
        for index, leg in enumerate(plan.radio_plans):
            tags.update(
                {
                    f"gain_controller:stream-{index}:{leg.gain_controller.mode.value}",
                    f"tuning:stream-{index}:ch{leg.starlink_channel}:{leg.starlink_edge.value}",
                }
            )
    elif isinstance(plan, CapturePlanV5):
        tags.update(
            {
                "PRODUCTION_DIRECT_ASYNC_RATES_V3",
                f"production_dwell_class:{plan.dwell_class.value}",
                "tuning_policy:same",
            }
        )
        for index, leg in enumerate(plan.radio_plans):
            tags.update(
                {
                    f"gain_controller:stream-{index}:{leg.gain_controller.mode.value}",
                    f"tuning:stream-{index}:ch{leg.starlink_channel}:{leg.starlink_edge.value}",
                }
            )
    return tags


def _validate_settings_readback(
    requested: RadioSettingsV1,
    actual: RadioSettingsV1,
    *,
    exact_rf_geometry: bool = False,
) -> None:
    for field in ("center_frequency_hz", "sample_rate_hz", "bandwidth_hz"):
        expected_value = int(getattr(requested, field))
        actual_value = int(getattr(actual, field))
        tolerance = 0 if exact_rf_geometry else max(1, round(expected_value * 1e-6))
        if abs(actual_value - expected_value) > tolerance:
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


def _truncate_iq_block(block: IqBlock, sample_count: int, sample_rate_hz: int) -> IqBlock:
    if not 0 < sample_count < block.metadata.sample_count:
        raise ValueError("IQ truncation must retain a strict non-empty prefix")
    document = block.metadata.model_dump(mode="json")
    document["sample_count"] = sample_count
    if isinstance(block.metadata, IqBlockMetadataV2):
        duration_ns = sample_count * 1_000_000_000 // sample_rate_hz
        for field in ("sample_time_realtime_ns", "sample_time_monotonic_ns"):
            interval = document.get(field)
            if interval is not None:
                interval["upper_ns"] = interval["lower_ns"] + duration_ns
    metadata = type(block.metadata).model_validate(document)
    return IqBlock(samples=block.samples[:sample_count].copy(), metadata=metadata)


def _log_gap(item: _PreparedRadio, metadata: IqBlockMetadataV2) -> None:
    assert metadata.device_sample_counter is not None
    _LOG.error(
        "radio=%s stream=%s expected_counter=%d actual_counter=%d "
        "missing_samples=%d missing_seconds=%.9f",
        item.identity.radio_id,
        metadata.stream_generation,
        metadata.device_sample_counter - metadata.missing_samples_before,
        metadata.device_sample_counter,
        metadata.missing_samples_before,
        metadata.missing_samples_before / item.applied_settings.sample_rate_hz,
    )


def _stream_timing(
    first: IqBlockMetadataV1,
    last: IqBlockMetadataV1,
    sample_rate_hz: int,
    captured_sample_count: int,
    release_target: int,
    release_observed: int,
    *,
    device_axis_sample_count: int | None = None,
) -> StreamTimingV1:
    if (
        isinstance(first, IqBlockMetadataV2)
        and isinstance(last, IqBlockMetadataV2)
        and first.sample_time_realtime_ns is not None
        and last.sample_time_realtime_ns is not None
    ):
        sample_period_ns = max(1, 1_000_000_000 // sample_rate_hz)
        first_estimate = first.sample_time_realtime_ns.lower_ns
        first_uncertainty = first.sample_time_uncertainty_ns or 0
        last_uncertainty = last.sample_time_uncertainty_ns or 0
        if device_axis_sample_count is None:
            last_estimate = max(
                first_estimate,
                last.sample_time_realtime_ns.upper_ns - sample_period_ns,
            )
        else:
            last_estimate = first_estimate + (
                (device_axis_sample_count - 1) * 1_000_000_000 // sample_rate_hz
            )
            last_uncertainty = max(first_uncertainty, last_uncertainty)
        return StreamTimingV1(
            release_target_monotonic_ns=release_target,
            release_observed_monotonic_ns=release_observed,
            first_sample=TimingEstimateV1(
                estimate_utc_ns=first_estimate,
                earliest_utc_ns=max(0, first_estimate - first_uncertainty),
                latest_utc_ns=first_estimate + first_uncertainty,
                method=TimingMethod.DEVICE_COUNTER_ANCHORED,
            ),
            last_sample=TimingEstimateV1(
                estimate_utc_ns=last_estimate,
                earliest_utc_ns=max(0, last_estimate - last_uncertainty),
                latest_utc_ns=last_estimate + last_uncertainty,
                method=TimingMethod.DEVICE_COUNTER_ANCHORED,
            ),
        )
    first_interval = first.host_request_utc_ns
    last_interval = last.host_request_utc_ns
    first_estimate = (first_interval.lower_ns + first_interval.upper_ns) // 2
    timing_sample_count = device_axis_sample_count or captured_sample_count
    nominal_duration_ns = (timing_sample_count - 1) * 1_000_000_000 // sample_rate_hz
    first_block_duration_ns = first.sample_count * 1_000_000_000 // sample_rate_hz
    if first.device_sample_counter is not None and last.device_sample_counter is not None:
        counter_sample_count = (
            device_axis_sample_count
            if device_axis_sample_count is not None
            else last.device_sample_counter + last.sample_count - first.device_sample_counter
        )
        counter_duration_ns = (counter_sample_count - 1) * 1_000_000_000 // sample_rate_hz
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


def _recording_stream(
    plan: CapturePlan,
    outcome: _StreamOutcome,
) -> RecordingStreamV1 | RecordingStreamV3:
    receipt = outcome.receipt
    if _device_axis_capture(plan):
        if not isinstance(plan, (CapturePlanV2, CapturePlanV3, CapturePlanV4, CapturePlanV5)):
            raise AcquisitionError("device-axis storage requires CapturePlanV2 or V3")
        if not isinstance(receipt, DeviceAxisStreamWriteReceipt):
            raise AcquisitionError("device-axis capture has no finalized V3 storage receipt")
        if outcome.applied_settings is None or outcome.timing is None:
            raise AcquisitionError("device-axis capture lacks applied settings or timing")
        if outcome.state is StreamState.FAILED:
            raise AcquisitionError("failed device-axis stream cannot be published")
        return RecordingStreamV3(
            stream_id=outcome.stream_id,
            radio=outcome.identity,
            requested_settings=outcome.requested_settings,
            applied_settings=outcome.applied_settings,
            state=cast(Literal[StreamState.COMPLETE, StreamState.PARTIAL], outcome.state),
            requested_sample_count=receipt.requested_sample_count,
            logical_sample_count=receipt.logical_sample_count,
            observed_sample_count=receipt.observed_sample_count,
            zero_fill_sample_count=receipt.zero_fill_sample_count,
            timing=outcome.timing,
            chunks=receipt.chunks,
            observed_iq_sha256=receipt.observed_iq_sha256,
            logical_iq_sha256=receipt.logical_iq_sha256,
            timeline_relative_path=receipt.timeline_relative_path,
            timeline_sha256=receipt.timeline_sha256,
            gap_map_relative_path=receipt.gap_map_relative_path,
            gap_map_sha256=receipt.gap_map_sha256,
            validity_inventory_relative_path=receipt.validity_inventory_relative_path,
            validity_inventory_sha256=receipt.validity_inventory_sha256,
            continuity=receipt.continuity,
            error=(
                None
                if outcome.state is StreamState.COMPLETE
                else (outcome.error or "capture observation integrity degraded")[:2048]
            ),
        )
    if isinstance(plan, (CapturePlanV3, CapturePlanV4, CapturePlanV5)):
        raise AcquisitionError("mixed-rate capture cannot publish legacy stream storage")
    chunks: tuple[RecordingChunkV1, ...]
    if outcome.state is StreamState.FAILED:
        if plan.schema_version == 2:
            profile = plan.profile_revision.profile
            continuity: ContinuitySummaryV1 | ContinuitySummaryV2 = ContinuitySummaryV2(
                refill_count=0,
                segment_count=0,
                observed_sample_count=0,
                device_span_sample_count=0,
                kernel_buffers=profile.kernel_buffers,
                queue_capacity_refills=profile.refill_queue_capacity,
                queue_high_water_refills=0,
            )
        else:
            continuity = ContinuitySummaryV1(refill_count=0, segment_count=0)
        chunks = ()
        timeline_path = None
        timeline_digest = None
    else:
        if receipt is None:
            raise AcquisitionError("captured stream has no finalized storage receipt")
        if not isinstance(receipt, StreamWriteReceipt):
            raise AcquisitionError("legacy capture has an incompatible storage receipt")
        continuity = receipt.continuity
        if plan.schema_version == 2 and not isinstance(continuity, ContinuitySummaryV2):
            raise AcquisitionError("V2 capture has no V2 storage continuity receipt")
        chunks = receipt.chunks
        timeline_path = receipt.timeline_relative_path
        timeline_digest = receipt.timeline_sha256
    document = {
        "stream_id": outcome.stream_id,
        "radio": outcome.identity,
        "requested_settings": outcome.requested_settings,
        "applied_settings": outcome.applied_settings,
        "state": outcome.state,
        "requested_sample_count": plan.resolved_sample_count,
        "captured_sample_count": outcome.captured_sample_count,
        "timing": outcome.timing,
        "chunks": chunks,
        "timeline_relative_path": timeline_path,
        "timeline_sha256": timeline_digest,
        "continuity": continuity,
        "error": (
            None
            if outcome.state is StreamState.COMPLETE
            else (outcome.error or "capture failed")[:2048]
        ),
    }
    if plan.schema_version == 2:
        return RecordingStreamV2.model_validate(
            {
                **document,
                "gap_map_relative_path": (
                    None if receipt is None else receipt.gap_map_relative_path
                ),
                "gap_map_sha256": None if receipt is None else receipt.gap_map_sha256,
            }
        )
    return RecordingStreamV1.model_validate(document)


def _synchronization_summary(
    plan: CapturePlan,
    streams: tuple[RecordingStreamV1 | RecordingStreamV3, ...],
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
    durations: list[int] = []
    for stream in timed:
        if isinstance(stream, RecordingStreamV3):
            span_samples = stream.logical_sample_count
        elif isinstance(stream.continuity, ContinuitySummaryV2):
            span_samples = stream.continuity.device_span_sample_count
        else:
            span_samples = stream.captured_sample_count
        durations.append(
            span_samples
            * 1_000_000_000
            // (stream.applied_settings or stream.requested_settings).sample_rate_hz
        )
    duration_a, duration_b = durations
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
        and (
            not isinstance(stream.continuity, ContinuitySummaryV2)
            or stream.continuity.enqueue_failure_count == 0
        )
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


def _device_buffer_request(
    profile: CaptureProfileV1, resolved_sample_count: int
) -> DeviceBufferRequestV1 | DirectAsyncRequest | None:
    """Preserve the published DDR resolver seam while adding direct-async policy."""

    if (
        DIRECT_ASYNC_PROFILE_TAG_V1 in profile.tags
        or DIRECT_ASYNC_RAM_DROP_PROFILE_TAG_V2 in profile.tags
        or DIRECT_ASYNC_RAM_DROP_PROFILE_TAG_V3 in profile.tags
    ):
        return device_buffer_request(profile, resolved_sample_count)
    return device_buffer_request_v1(profile, resolved_sample_count)


def _failed_outcome(
    item: _PreparedRadio,
    error: str,
    *,
    storage_fatal: bool = False,
    interruption: BaseException | None = None,
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
        interruption=interruption,
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


def _close_sources(sources: tuple[RadioSource, ...]) -> _SourceCloseOutcome:
    errors: list[str] = []
    interruption: BaseException | None = None
    for source in sources:
        try:
            source.close()
        except BaseException as error:
            errors.append(f"{source.identity.radio_id} close failed: {_error_text(error)}")
            if not isinstance(error, Exception) and interruption is None:
                interruption = error
    return _SourceCloseOutcome(errors=tuple(errors), interruption=interruption)


def _raise_source_close_interruption(outcome: _SourceCloseOutcome) -> None:
    if outcome.interruption is not None:
        raise outcome.interruption


def _error_text(error: BaseException) -> str:
    message = str(error).strip()
    return f"{type(error).__name__}: {message}" if message else type(error).__name__


def _canonical_errors(errors: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(error[:2048] for error in errors if error))
