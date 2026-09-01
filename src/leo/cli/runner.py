"""One foreground supervisor for scheduled recording and scanner capture."""

from __future__ import annotations

import hashlib
import logging
import os
import re
import secrets
import signal
import socket
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from threading import Event, current_thread, main_thread
from time import monotonic
from types import FrameType
from typing import Any, cast

from leo.acquisition import (
    AcquisitionBackpressureController,
    AcquisitionQueuePressurePort,
    AcquisitionSupervisorPoisoned,
    CaptureTaskKind,
)
from leo.acquisition.mixed_rate_schedule import (
    PRODUCTION_DIRECT_ASYNC_HOLD_ROLLOUT_POLICY_V1,
    compile_production_dwell_intent_hold_rollout_v1,
    compile_production_dwell_intent_v1,
    compile_production_dwell_intent_v2,
    compile_production_dwell_intent_v3,
)
from leo.cli.backend import (
    AcquisitionCliBackend,
    CliBackendError,
    ScheduledScannerPort,
)
from leo.cli.models import (
    CaptureDataV1,
    ExitCode,
    RunDataV1,
    RunDataV2,
    ScheduledDwellPayloadV1,
)
from leo.contracts.capture_control import (
    CaptureControlStateV1,
    CaptureDesiredState,
    CaptureObservedState,
)
from leo.contracts.mixed_rate_schedule import (
    MIXED_RATE_10M_SCHEDULE_POLICY_V1,
    MIXED_RATE_SAFE_SCHEDULE_POLICY_V1,
    MIXED_RATE_SCHEDULE_POLICY_V1,
    PRODUCTION_2P5_10_15_RATE_POLICY_V2,
    PRODUCTION_DIRECT_ASYNC_RATE_POLICY_V3,
    PRODUCTION_NATIVE_RATE_POLICY_V2,
    ProductionDwellClass,
    ProductionDwellIntentV1,
    ProductionDwellIntentV2,
    ProductionDwellIntentV3,
)
from leo.contracts.states import CaptureState
from leo.scanner import ScannerCaptureBurstReportLike

logger = logging.getLogger(__name__)
_MIXED_RATE_POLICIES = frozenset(
    {
        MIXED_RATE_SCHEDULE_POLICY_V1,
        MIXED_RATE_10M_SCHEDULE_POLICY_V1,
        MIXED_RATE_SAFE_SCHEDULE_POLICY_V1,
        PRODUCTION_NATIVE_RATE_POLICY_V2,
        PRODUCTION_2P5_10_15_RATE_POLICY_V2,
        PRODUCTION_DIRECT_ASYNC_RATE_POLICY_V3,
        PRODUCTION_DIRECT_ASYNC_HOLD_ROLLOUT_POLICY_V1,
    }
)
_PRODUCTION_RATE_POLICIES_V2 = frozenset(
    {
        PRODUCTION_NATIVE_RATE_POLICY_V2,
        PRODUCTION_2P5_10_15_RATE_POLICY_V2,
    }
)
_PRODUCTION_RATE_POLICIES_V3 = frozenset(
    {
        PRODUCTION_DIRECT_ASYNC_RATE_POLICY_V3,
        PRODUCTION_DIRECT_ASYNC_HOLD_ROLLOUT_POLICY_V1,
    }
)
_PRODUCTION_RATE_POLICIES = _PRODUCTION_RATE_POLICIES_V2 | _PRODUCTION_RATE_POLICIES_V3
ProfileSelector = Callable[[tuple[str, ...], str], str]
RunData = RunDataV1 | RunDataV2

_RUNNING_CONTROL = CaptureControlStateV1(
    generation=0,
    desired_state=CaptureDesiredState.RUNNING,
    observed_state=CaptureObservedState.RUNNING,
    changed_utc_ns=0,
    operator_id="in-process",
    reason="backend has no durable capture authority",
)


def _uniform_profile_selector(profile_names: tuple[str, ...], selection_key: str) -> str:
    """Map an unpredictable or durable key to an unbiased profile index."""

    modulus = len(profile_names)
    sample_space = 1 << 256
    rejection_floor = sample_space - (sample_space % modulus)
    counter = 0
    while True:
        digest = hashlib.sha256(
            f"profile-selection-v1\0{selection_key}\0{counter}".encode()
        ).digest()
        value = int.from_bytes(digest, "big")
        if value < rejection_floor:
            return profile_names[value % modulus]
        counter += 1


class ContinuousAcquisitionRunner:
    """Schedule all radio work through one pause-aware supervisor."""

    def __init__(
        self,
        backend: AcquisitionCliBackend,
        *,
        queue_pressure: AcquisitionQueuePressurePort | None = None,
        backpressure: AcquisitionBackpressureController | None = None,
        clock=monotonic,
        zero_interval_backpressure_poll_seconds: float = 1.0,
        capture_control_poll_seconds: float = 0.25,
        radio_busy_retry_seconds: float = 1.0,
        utc_now=lambda: datetime.now(UTC),
        profile_selector: ProfileSelector = _uniform_profile_selector,
    ) -> None:
        if zero_interval_backpressure_poll_seconds <= 0:
            raise ValueError("backpressure poll interval must be positive")
        if capture_control_poll_seconds <= 0 or radio_busy_retry_seconds <= 0:
            raise ValueError("capture supervisor poll intervals must be positive")
        self.backend = backend
        self.queue_pressure = backend if queue_pressure is None else queue_pressure
        self.backpressure = backpressure or AcquisitionBackpressureController()
        self._clock = clock
        self._zero_interval_backpressure_poll_seconds = zero_interval_backpressure_poll_seconds
        self._capture_control_poll_seconds = capture_control_poll_seconds
        self._radio_busy_retry_seconds = radio_busy_retry_seconds
        self._utc_now = utc_now
        self._profile_selector = profile_selector

    def run(
        self,
        profile_name: str | Sequence[str],
        *,
        radio_ids: Sequence[str],
        extra_tags: tuple[str, ...],
        interval_seconds: float,
        maximum_captures: int | None,
        cancel: Event,
        mixed_rate_policy: str | None = None,
    ) -> RunData:
        if interval_seconds < 0:
            raise ValueError("capture interval cannot be negative")
        if maximum_captures is not None and maximum_captures <= 0:
            raise ValueError("maximum captures must be positive")
        if mixed_rate_policy is not None and mixed_rate_policy not in _MIXED_RATE_POLICIES:
            raise ValueError("unsupported mixed-rate dwell policy")
        if mixed_rate_policy is not None and interval_seconds <= 0:
            raise ValueError("mixed-rate dwell policy requires a positive cadence interval")
        profile_names = _profile_pool(profile_name)
        resolved_radio_ids = tuple(radio_ids)
        if len(profile_names) > 1 and not resolved_radio_ids:
            resolved_radio_ids = tuple(
                radio.radio_id for radio in self.backend.radios(probe=False).radios
            )
        if len(profile_names) > 1 and (
            len(resolved_radio_ids) != 2 or len(set(resolved_radio_ids)) != 2
        ):
            raise ValueError("multi-profile acquisition requires exactly two unique radios")
        scanner = _scheduled_scanner(self.backend)
        if scanner is not None and _durable_acquisition_queue(self.backend):
            return self._run_durable_supervised(
                profile_names,
                radio_ids=resolved_radio_ids,
                extra_tags=extra_tags,
                interval_seconds=interval_seconds,
                maximum_captures=maximum_captures,
                cancel=cancel,
                scanner=scanner,
                mixed_rate_policy=mixed_rate_policy,
            )
        if mixed_rate_policy is not None:
            raise ValueError("mixed-rate dwell policy requires the durable acquisition queue")
        control_reader = getattr(self.backend, "capture_control_snapshot", None)
        if scanner is None and not callable(control_reader):
            return self._run_capture_only(
                profile_names,
                radio_ids=resolved_radio_ids,
                extra_tags=extra_tags,
                interval_seconds=interval_seconds,
                maximum_captures=maximum_captures,
                cancel=cancel,
            )
        return self._run_supervised(
            profile_names,
            radio_ids=resolved_radio_ids,
            extra_tags=extra_tags,
            interval_seconds=interval_seconds,
            maximum_captures=maximum_captures,
            cancel=cancel,
            scanner=scanner,
        )

    def _run_durable_supervised(
        self,
        profile_names: tuple[str, ...],
        *,
        radio_ids: Sequence[str],
        extra_tags: tuple[str, ...],
        interval_seconds: float,
        maximum_captures: int | None,
        cancel: Event,
        scanner: ScheduledScannerPort,
        mixed_rate_policy: str | None,
    ) -> RunData:
        """Persist cadence ticks before admission and dispatch one global lease."""

        queue = cast(Any, self.backend)
        worker_id = f"capture-supervisor:{socket.gethostname()}:{os.getpid()}"
        lease_for = timedelta(minutes=10)
        scanner_configuration = scanner.scanner_schedule()
        if scanner_configuration is not None:
            scanner.reconcile_scanner_recordings()
        count = committed = degraded = failed = 0
        last: CaptureDataV1 | None = None
        next_due = _cadence_floor(self._utc_now(), interval_seconds)
        rate_profile_authority = (
            None
            if mixed_rate_policy is None or mixed_rate_policy in _PRODUCTION_RATE_POLICIES
            else self.backend.mixed_rate_profile_authority()
        )
        production_profile_authority = (
            self.backend.production_profile_authority()
            if mixed_rate_policy in _PRODUCTION_RATE_POLICIES
            else None
        )

        queue.reclaim_expired_acquisition_operations()
        with cancellation_signals(cancel):
            while not cancel.is_set():
                now_utc = self._utc_now()
                if now_utc >= next_due:
                    key_profiles = (
                        profile_names
                        if mixed_rate_policy is None
                        else (*profile_names, mixed_rate_policy)
                    )
                    if production_profile_authority is not None:
                        key_profiles = (
                            *key_profiles,
                            _production_profile_authority_identity(production_profile_authority),
                        )
                    key = _scheduled_dwell_key(key_profiles, next_due, interval_seconds)
                    if mixed_rate_policy is None:
                        selected_profile = self._select_profile(
                            profile_names,
                            selection_key=key,
                        )
                        dwell_payload = ScheduledDwellPayloadV1(
                            profile_name=selected_profile,
                            profile_names=profile_names,
                            selection_policy=(
                                "single" if len(profile_names) == 1 else "uniform_per_dwell"
                            ),
                            radio_ids=tuple(radio_ids),
                            extra_tags=extra_tags,
                        )
                        serialized_payload = dwell_payload.model_dump(mode="json")
                        if len(profile_names) == 1:
                            # Keep the existing durable single-profile payload shape;
                            # the typed reader supplies the new defaults.
                            serialized_payload = {
                                "profile_name": selected_profile,
                                "radio_ids": list(radio_ids),
                                "extra_tags": list(extra_tags),
                            }
                    else:
                        if mixed_rate_policy in _PRODUCTION_RATE_POLICIES:
                            assert production_profile_authority is not None
                            required_profiles = {
                                "starlink-ch4-lower-2p5m-60s-native-bandwidth-v4",
                                "starlink-ch4-lower-5m-60s-native-bandwidth-v4",
                            }
                            if set(profile_names) != required_profiles:
                                raise ValueError(
                                    "production policy requires exactly the reviewed 2.5 and "
                                    "5 MS/s service bootstrap profiles"
                                )
                            if mixed_rate_policy in _PRODUCTION_RATE_POLICIES_V3:
                                intent: ProductionDwellIntentV2 | ProductionDwellIntentV3
                                if (
                                    mixed_rate_policy
                                    == PRODUCTION_DIRECT_ASYNC_HOLD_ROLLOUT_POLICY_V1
                                ):
                                    intent = compile_production_dwell_intent_hold_rollout_v1(
                                        operation_key=key,
                                        cadence_ordinal=_cadence_ordinal(
                                            next_due, interval_seconds
                                        ),
                                        radio_ids=radio_ids,
                                        profile_authority=production_profile_authority,
                                        rollout_policy_id=mixed_rate_policy,
                                        extra_tags=extra_tags,
                                    )
                                else:
                                    intent = compile_production_dwell_intent_v3(
                                        operation_key=key,
                                        cadence_ordinal=_cadence_ordinal(
                                            next_due, interval_seconds
                                        ),
                                        radio_ids=radio_ids,
                                        profile_authority=production_profile_authority,
                                        policy_id=mixed_rate_policy,
                                        extra_tags=extra_tags,
                                    )
                            else:
                                intent = compile_production_dwell_intent_v2(
                                    operation_key=key,
                                    cadence_ordinal=_cadence_ordinal(next_due, interval_seconds),
                                    radio_ids=radio_ids,
                                    profile_authority=production_profile_authority,
                                    policy_id=mixed_rate_policy,
                                    extra_tags=extra_tags,
                                )
                        else:
                            assert rate_profile_authority is not None
                            legacy_intent = compile_production_dwell_intent_v1(
                                operation_key=key,
                                cadence_ordinal=_cadence_ordinal(next_due, interval_seconds),
                                ordinary_profile_names=profile_names,
                                radio_ids=radio_ids,
                                rate_profile_authority=rate_profile_authority,
                                policy_id=mixed_rate_policy,
                                extra_tags=extra_tags,
                            )
                            serialized_payload = legacy_intent.model_dump(mode="json")
                        if mixed_rate_policy in _PRODUCTION_RATE_POLICIES:
                            serialized_payload = intent.model_dump(mode="json")
                    queue.enqueue_acquisition_operation(
                        operation_key=key,
                        kind=CaptureTaskKind.SCHEDULED_RECORDING.value,
                        payload=serialized_payload,
                        scheduled_for=next_due,
                        coalesce_pending_kind=True,
                    )
                    next_due = (
                        next_due + timedelta(seconds=interval_seconds)
                        if interval_seconds > 0
                        else now_utc + timedelta(microseconds=1)
                    )

                control = self._capture_control_snapshot()
                if control is None or control.desired_state is CaptureDesiredState.PAUSED:
                    if cancel.wait(self._capture_control_poll_seconds):
                        break
                    continue

                active = queue.active_acquisition_operations(limit=1)
                if not active:
                    if cancel.wait(self._capture_control_poll_seconds):
                        break
                    continue
                head = active[0]
                if head.state == "leased":
                    if cancel.wait(self._capture_control_poll_seconds):
                        break
                    queue.reclaim_expired_acquisition_operations()
                    continue
                if (
                    head.kind == CaptureTaskKind.SCHEDULED_RECORDING.value
                    and not self._admit_scheduled_dwell()
                ):
                    # Backpressure suppresses execution, not the durable intent.
                    if cancel.wait(self._zero_interval_backpressure_poll_seconds):
                        break
                    continue

                lease = queue.claim_acquisition_operation(worker_id=worker_id, lease_for=lease_for)
                if lease is None:
                    if cancel.wait(self._radio_busy_retry_seconds):
                        break
                    continue
                try:
                    if lease.kind == CaptureTaskKind.SCHEDULED_RECORDING.value:
                        if lease.payload.get("policy_id") in _PRODUCTION_RATE_POLICIES:
                            production_intent = (
                                ProductionDwellIntentV3.model_validate(lease.payload)
                                if lease.payload.get("policy_id") in _PRODUCTION_RATE_POLICIES_V3
                                else ProductionDwellIntentV2.model_validate(lease.payload)
                            )
                            last = self.backend.capture_production_once(
                                production_intent,
                                session_id=None,
                                cancel=cancel,
                                task_kind=CaptureTaskKind.SCHEDULED_RECORDING.value,
                            )
                        elif lease.payload.get("policy_id") in _MIXED_RATE_POLICIES:
                            legacy_intent = ProductionDwellIntentV1.model_validate(lease.payload)
                            if legacy_intent.dwell_class is ProductionDwellClass.ORDINARY_POOL:
                                assert legacy_intent.ordinary_profile_name is not None
                                last = self.backend.capture_once(
                                    legacy_intent.ordinary_profile_name,
                                    radio_ids=legacy_intent.radio_ids,
                                    session_id=None,
                                    extra_tags=legacy_intent.extra_tags,
                                    cancel=cancel,
                                    task_kind=CaptureTaskKind.SCHEDULED_RECORDING.value,
                                )
                            else:
                                last = self.backend.capture_mixed_once(
                                    legacy_intent,
                                    session_id=None,
                                    cancel=cancel,
                                    task_kind=CaptureTaskKind.SCHEDULED_RECORDING.value,
                                )
                        else:
                            payload = ScheduledDwellPayloadV1.model_validate(lease.payload)
                            last = self.backend.capture_once(
                                payload.profile_name,
                                radio_ids=payload.radio_ids,
                                session_id=None,
                                extra_tags=payload.extra_tags,
                                cancel=cancel,
                                task_kind=CaptureTaskKind.SCHEDULED_RECORDING.value,
                            )
                        count, committed, degraded, failed = _record_capture_result(
                            last,
                            count=count,
                            committed=committed,
                            degraded=degraded,
                            failed=failed,
                        )
                        health_failure = _scheduled_capture_health_failure(last)
                        if health_failure is not None:
                            queue.fail_acquisition_operation(
                                operation_id=lease.operation_id,
                                worker_id=worker_id,
                                error=health_failure,
                                retryable=False,
                            )
                        else:
                            queue.complete_acquisition_operation(
                                operation_id=lease.operation_id,
                                worker_id=worker_id,
                                outcome=f"capture {last.session_id} {last.state.value}",
                            )
                        if (
                            scanner_configuration is not None
                            and health_failure is None
                            and last.state
                            in {
                                CaptureState.COMMITTED,
                                CaptureState.DEGRADED,
                            }
                        ):
                            queue.enqueue_acquisition_operation(
                                operation_key=f"scan-after:{lease.operation_key}",
                                kind=CaptureTaskKind.SCANNER_SWEEP.value,
                                payload={"after_operation_id": lease.operation_id},
                                # Place the scan immediately after its parent
                                # even when several overdue cadence slots were
                                # materialized during backpressure.
                                scheduled_for=lease.scheduled_for + timedelta(microseconds=1),
                                coalesce_pending_kind=True,
                            )
                        if maximum_captures is not None and count >= maximum_captures:
                            return _run_result(
                                profile_names,
                                "maximum_captures",
                                count,
                                committed,
                                degraded,
                                failed,
                                last,
                            )
                    elif lease.kind == CaptureTaskKind.SCANNER_SWEEP.value:
                        captured = scanner.capture_scheduled_scanner()
                        burst = scanner.analyze_scheduled_scanner(captured)
                        queue.complete_acquisition_operation(
                            operation_id=lease.operation_id,
                            worker_id=worker_id,
                            outcome=(
                                f"scan burst {burst.burst_id} published; "
                                f"scans={len(burst.reports)}; "
                                f"active_edges={burst.active_edge_count}"
                            ),
                        )
                    else:
                        queue.fail_acquisition_operation(
                            operation_id=lease.operation_id,
                            worker_id=worker_id,
                            error=f"supervisor cannot dispatch kind {lease.kind}",
                            retryable=False,
                        )
                except AcquisitionSupervisorPoisoned as error:
                    queue.fail_acquisition_operation(
                        operation_id=lease.operation_id,
                        worker_id=worker_id,
                        error=_poisoned_supervisor_error(error),
                        retryable=False,
                    )
                    logger.critical(
                        "acquisition_supervisor_poisoned session=%s errors=%s",
                        error.session_id,
                        error.errors,
                    )
                    raise
                except CliBackendError as error:
                    retryable = error.exit_code == ExitCode.CONFLICT
                    queue.fail_acquisition_operation(
                        operation_id=lease.operation_id,
                        worker_id=worker_id,
                        error=str(error),
                        retryable=retryable,
                        retry_after=timedelta(seconds=self._radio_busy_retry_seconds),
                    )
                    if not retryable:
                        return _run_result(
                            profile_names,
                            "error",
                            count,
                            committed,
                            degraded,
                            failed,
                            last,
                            error=str(error),
                        )
                except Exception as error:
                    queue.fail_acquisition_operation(
                        operation_id=lease.operation_id,
                        worker_id=worker_id,
                        error=f"{type(error).__name__}: {error}",
                        retryable=True,
                        retry_after=timedelta(seconds=self._radio_busy_retry_seconds),
                    )
                    logger.exception("durable_acquisition_operation_failed")

        return _run_result(profile_names, "cancelled", count, committed, degraded, failed, last)

    def _run_capture_only(
        self,
        profile_names: tuple[str, ...],
        *,
        radio_ids: Sequence[str],
        extra_tags: tuple[str, ...],
        interval_seconds: float,
        maximum_captures: int | None,
        cancel: Event,
    ) -> RunData:
        """Compatibility path for small fakes without capture-control ports."""

        count = committed = degraded = failed = 0
        last: CaptureDataV1 | None = None
        with cancellation_signals(cancel):
            while not cancel.is_set():
                if not self._admit_scheduled_dwell():
                    delay = (
                        interval_seconds
                        if interval_seconds > 0
                        else self._zero_interval_backpressure_poll_seconds
                    )
                    if cancel.wait(delay):
                        break
                    continue
                capture_started = self._clock()
                try:
                    selected_profile = self._select_profile(profile_names)
                    last = self.backend.capture_once(
                        selected_profile,
                        radio_ids=radio_ids,
                        session_id=None,
                        extra_tags=extra_tags,
                        cancel=cancel,
                        task_kind=CaptureTaskKind.SCHEDULED_RECORDING.value,
                    )
                except KeyboardInterrupt:
                    cancel.set()
                    break
                count, committed, degraded, failed = _record_capture_result(
                    last,
                    count=count,
                    committed=committed,
                    degraded=degraded,
                    failed=failed,
                )
                if maximum_captures is not None and count >= maximum_captures:
                    return _run_result(
                        profile_names,
                        "maximum_captures",
                        count,
                        committed,
                        degraded,
                        failed,
                        last,
                    )
                remaining = max(0.0, interval_seconds - (self._clock() - capture_started))
                if remaining and cancel.wait(remaining):
                    break
        return _run_result(
            profile_names,
            "cancelled",
            count,
            committed,
            degraded,
            failed,
            last,
        )

    def _run_supervised(
        self,
        profile_names: tuple[str, ...],
        *,
        radio_ids: Sequence[str],
        extra_tags: tuple[str, ...],
        interval_seconds: float,
        maximum_captures: int | None,
        cancel: Event,
        scanner: ScheduledScannerPort | None,
    ) -> RunData:
        count = committed = degraded = failed = 0
        last: CaptureDataV1 | None = None
        now = self._clock()
        next_capture_due = now
        scanner_configuration = scanner.scanner_schedule() if scanner is not None else None
        if scanner is not None and scanner_configuration is not None:
            scanner.reconcile_scanner_recordings()
        next_scanner_due: float | None = None
        last_scanner_capture: float | None = None
        pause_observed = False
        pending_profile_name: str | None = None
        analysis: Future[ScannerCaptureBurstReportLike] | None = None

        with (
            cancellation_signals(cancel),
            ThreadPoolExecutor(
                max_workers=1,
                thread_name_prefix="leo-scanner-analysis",
            ) as analysis_pool,
        ):
            while not cancel.is_set():
                analysis = _reap_scanner_analysis(analysis)
                control = self._capture_control_snapshot()
                if control is None or control.desired_state is CaptureDesiredState.PAUSED:
                    pause_observed = True
                    if cancel.wait(self._capture_control_poll_seconds):
                        break
                    continue

                now = self._clock()
                if pause_observed:
                    next_capture_due = now
                    next_scanner_due = None
                    last_scanner_capture = None
                    pending_profile_name = None
                    pause_observed = False

                if now >= next_capture_due:
                    if pending_profile_name is None:
                        pending_profile_name = self._select_profile(profile_names)
                    if not self._admit_scheduled_dwell():
                        delay = (
                            interval_seconds
                            if interval_seconds > 0
                            else self._zero_interval_backpressure_poll_seconds
                        )
                        next_capture_due = now + delay
                        continue
                    capture_started = now
                    try:
                        last = self.backend.capture_once(
                            pending_profile_name,
                            radio_ids=radio_ids,
                            session_id=None,
                            extra_tags=extra_tags,
                            cancel=cancel,
                            task_kind=CaptureTaskKind.SCHEDULED_RECORDING.value,
                        )
                    except CliBackendError as error:
                        if error.exit_code == ExitCode.CONFLICT:
                            logger.info("scheduled_capture_deferred reason=%s", error)
                            next_capture_due = self._clock() + self._radio_busy_retry_seconds
                            continue
                        return _run_result(
                            profile_names,
                            "error",
                            count,
                            committed,
                            degraded,
                            failed,
                            last,
                            error=str(error),
                        )
                    count, committed, degraded, failed = _record_capture_result(
                        last,
                        count=count,
                        committed=committed,
                        degraded=degraded,
                        failed=failed,
                    )
                    pending_profile_name = None
                    if maximum_captures is not None and count >= maximum_captures:
                        return _run_result(
                            profile_names,
                            "maximum_captures",
                            count,
                            committed,
                            degraded,
                            failed,
                            last,
                        )
                    next_capture_due = (
                        capture_started + interval_seconds
                        if interval_seconds > 0
                        else self._clock()
                    )
                    if scanner_configuration is not None and last.state in {
                        CaptureState.COMMITTED,
                        CaptureState.DEGRADED,
                    }:
                        captured_at = self._clock()
                        next_scanner_due = (
                            captured_at
                            if last_scanner_capture is None
                            else max(
                                captured_at,
                                last_scanner_capture + scanner_configuration.interval_seconds,
                            )
                        )
                    continue

                if (
                    scanner is not None
                    and scanner_configuration is not None
                    and next_scanner_due is not None
                    and now >= next_scanner_due
                ):
                    lateness = now - next_scanner_due
                    if lateness > scanner_configuration.maximum_lateness_seconds:
                        logger.warning(
                            "scheduled_scanner_late lateness_seconds=%.3f",
                            lateness,
                        )
                    if analysis is not None:
                        next_scanner_due = now + self._radio_busy_retry_seconds
                        logger.info("scheduled_scanner_deferred reason=analysis_busy")
                    else:
                        try:
                            captured = scanner.capture_scheduled_scanner()
                        except CliBackendError as error:
                            level = (
                                logging.INFO
                                if error.exit_code == ExitCode.CONFLICT
                                else logging.ERROR
                            )
                            logger.log(level, "scheduled_scanner_not_started reason=%s", error)
                            next_scanner_due = now + self._radio_busy_retry_seconds
                        else:
                            last_scanner_capture = now
                            next_scanner_due = None
                            analysis = analysis_pool.submit(
                                scanner.analyze_scheduled_scanner,
                                captured,
                            )
                    continue

                due = [next_capture_due]
                if next_scanner_due is not None:
                    due.append(next_scanner_due)
                delay = max(0.0, min(due) - now)
                if delay and cancel.wait(delay):
                    break

        return _run_result(
            profile_names,
            "cancelled",
            count,
            committed,
            degraded,
            failed,
            last,
        )

    def _select_profile(
        self,
        profile_names: tuple[str, ...],
        *,
        selection_key: str | None = None,
    ) -> str:
        if len(profile_names) == 1:
            return profile_names[0]
        selected = self._profile_selector(
            profile_names,
            selection_key or secrets.token_hex(32),
        )
        if selected not in profile_names:
            raise ValueError("profile selector returned a value outside the configured pool")
        return selected

    def _capture_control_snapshot(self) -> CaptureControlStateV1 | None:
        reader = getattr(self.backend, "capture_control_snapshot", None)
        if not callable(reader):
            return _RUNNING_CONTROL
        try:
            return cast(CaptureControlStateV1, reader())
        except Exception as error:
            logger.error(
                "capture_control_unavailable suppressed=true error_type=%s error=%s",
                type(error).__name__,
                error,
            )
            return None

    def _admit_scheduled_dwell(self) -> bool:
        try:
            pressure = self.queue_pressure.acquisition_queue_pressure()
        except Exception as error:
            decision = self.backpressure.unavailable()
            logger.warning(
                "acquisition_backpressure queued=unknown running=unknown "
                "suppressed=true transition=%s enter_above=%d exit_below=%d "
                "error_type=%s error=%s",
                decision.transition,
                self.backpressure.enter_above,
                self.backpressure.exit_below,
                type(error).__name__,
                error,
            )
            return False
        decision = self.backpressure.observe(pressure)
        logger.info(
            "acquisition_backpressure queued=%d running=%d suppressed=%s transition=%s "
            "enter_above=%d exit_below=%d",
            pressure.queued,
            pressure.running,
            str(decision.suppressed).lower(),
            decision.transition,
            self.backpressure.enter_above,
            self.backpressure.exit_below,
        )
        return decision.admitted


@contextmanager
def cancellation_signals(cancel: Event):
    """Translate SIGINT/SIGTERM into the same cooperative capture event."""

    if current_thread() is not main_thread():
        yield
        return
    previous: dict[signal.Signals, Any] = {}

    def handle(_signal: int, _frame: FrameType | None) -> None:
        cancel.set()

    try:
        for signum in (signal.SIGINT, signal.SIGTERM):
            previous[signum] = signal.getsignal(signum)
            signal.signal(signum, handle)
        yield
    finally:
        for signum, handler in previous.items():
            signal.signal(signum, handler)


def _scheduled_scanner(backend: AcquisitionCliBackend) -> ScheduledScannerPort | None:
    required = (
        "reconcile_scanner_recordings",
        "scanner_schedule",
        "capture_scheduled_scanner",
        "analyze_scheduled_scanner",
    )
    if all(callable(getattr(backend, name, None)) for name in required):
        return cast(ScheduledScannerPort, backend)
    return None


def _durable_acquisition_queue(backend: AcquisitionCliBackend) -> bool:
    required = (
        "enqueue_acquisition_operation",
        "active_acquisition_operations",
        "claim_acquisition_operation",
        "complete_acquisition_operation",
        "fail_acquisition_operation",
        "reclaim_expired_acquisition_operations",
    )
    return all(callable(getattr(backend, name, None)) for name in required)


def _cadence_floor(now: datetime, interval_seconds: float) -> datetime:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("acquisition scheduling clock must be timezone-aware")
    canonical = now.astimezone(UTC)
    if interval_seconds == 0:
        return canonical
    slot = int(canonical.timestamp() // interval_seconds)
    return datetime.fromtimestamp(slot * interval_seconds, tz=UTC)


def _cadence_ordinal(scheduled_for: datetime, interval_seconds: float) -> int:
    if interval_seconds <= 0:
        raise ValueError("cadence ordinal requires a positive interval")
    if scheduled_for.tzinfo is None or scheduled_for.utcoffset() is None:
        raise ValueError("cadence scheduling clock must be timezone-aware")
    return int(scheduled_for.astimezone(UTC).timestamp() // interval_seconds)


def _profile_pool(profile_name: str | Sequence[str]) -> tuple[str, ...]:
    profile_names = (profile_name,) if isinstance(profile_name, str) else tuple(profile_name)
    if not profile_names:
        raise ValueError("acquisition run requires at least one profile")
    if any(not name or name != name.strip() for name in profile_names):
        raise ValueError("acquisition profile names must be non-empty exact values")
    if len(set(profile_names)) != len(profile_names):
        raise ValueError("acquisition profile names must be unique")
    return profile_names


def _scheduled_dwell_key(
    profile_name: str | Sequence[str],
    scheduled_for: datetime,
    interval_seconds: float,
) -> str:
    profile_names = _profile_pool(profile_name)
    # Preserve the published single-profile operation keys. A multi-profile key
    # identifies the configured pool, not the randomly selected member: if the
    # same cadence slot is enqueued again after a restart, the queue retains the
    # original persisted selection instead of silently rerolling it.
    identity = profile_names[0] if len(profile_names) == 1 else "\0".join(profile_names)
    profile_digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
    if interval_seconds == 0:
        return (
            f"scheduled-dwell:{profile_digest}:{scheduled_for.isoformat(timespec='microseconds')}"
        )
    return f"scheduled-dwell:{profile_digest}:{scheduled_for.isoformat(timespec='seconds')}"


def _production_profile_authority_identity(
    authority: Mapping[
        tuple[int, tuple[int, ...], bool],
        tuple[str, str, int],
    ],
) -> str:
    """Bind a production cadence key to its exact immutable profile authority."""

    digest = hashlib.sha256()
    for (rate, receivers, mixed), (profile, revision, refill_samples) in sorted(authority.items()):
        digest.update(
            (
                f"{rate}\0{','.join(str(receiver) for receiver in receivers)}\0"
                f"{int(mixed)}\0{profile}\0{revision}\0{refill_samples}\n"
            ).encode()
        )
    return f"production-profile-authority-v1:{digest.hexdigest()}"


def _reap_scanner_analysis(
    future: Future[ScannerCaptureBurstReportLike] | None,
) -> Future[ScannerCaptureBurstReportLike] | None:
    if future is None or not future.done():
        return future
    try:
        burst = future.result()
    except Exception:
        logger.exception("scheduled_scanner_analysis_failed")
    else:
        logger.info(
            "scheduled_scanner_completed burst_id=%s scans=%d active_edges=%d",
            burst.burst_id,
            len(burst.reports),
            burst.active_edge_count,
        )
    return None


def _record_capture_result(
    result: CaptureDataV1,
    *,
    count: int,
    committed: int,
    degraded: int,
    failed: int,
) -> tuple[int, int, int, int]:
    count += 1
    if result.state is CaptureState.COMMITTED:
        committed += 1
    elif result.state is CaptureState.DEGRADED:
        degraded += 1
    else:
        failed += 1
    return count, committed, degraded, failed


_INTEGRITY_DEGRADED_PATTERN = re.compile(
    r"^[^:]+: capture integrity degraded: "
    r"gaps=\d+, missing_samples=\d+, overflows=\d+, "
    r"enqueue_failures=(\d+), device_span=(\d+)/(\d+)$"
)
_TERMINAL_CAPTURE_ERROR_MARKERS = (
    "refill queue full; capture cannot drain rf without blocking",
    "terminal enqueue",
    "storage consumer failed:",
    "capture produced no publishable IQ",
)


def _scheduled_capture_health_failure(result: CaptureDataV1) -> str | None:
    unhealthy = result.state is CaptureState.FAILED
    for error in result.errors:
        if any(marker in error.lower() for marker in _TERMINAL_CAPTURE_ERROR_MARKERS):
            unhealthy = True
    if result.state is CaptureState.DEGRADED:
        if not result.errors:
            unhealthy = True
        for error in result.errors:
            match = _INTEGRITY_DEGRADED_PATTERN.fullmatch(error)
            if match is None:
                unhealthy = True
                continue
            enqueue_failures, observed, required = (int(value) for value in match.groups())
            if enqueue_failures != 0 or observed != required:
                unhealthy = True
    if not unhealthy:
        return None
    detail = "; ".join(result.errors)
    message = (
        f"capture {result.session_id} {result.state.value}; "
        "scheduled capture health rejected terminal or truncated evidence"
    )
    return f"{message}: {detail}" if detail else message


def _poisoned_supervisor_error(error: AcquisitionSupervisorPoisoned) -> str:
    detail = "; ".join(error.errors)
    message = f"{type(error).__name__}: {error}"
    return f"{message}: {detail}" if detail else message


def _run_result(
    profile_names: tuple[str, ...],
    reason: str,
    count: int,
    committed: int,
    degraded: int,
    failed: int,
    last: CaptureDataV1 | None,
    *,
    error: str | None = None,
) -> RunData:
    common = dict(
        stopped_reason=cast(Any, reason),
        capture_count=count,
        committed_count=committed,
        degraded_count=degraded,
        failed_count=failed,
        last_capture=last,
        error=error,
    )
    if len(profile_names) == 1:
        return RunDataV1(profile_name=profile_names[0], **common)
    return RunDataV2(profile_names=profile_names, **common)
