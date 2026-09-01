from __future__ import annotations

from datetime import UTC, datetime, timedelta
from threading import Event, Thread
from types import SimpleNamespace
from typing import cast

import pytest

from leo.acquisition import AcquisitionQueuePressure, AcquisitionSupervisorPoisoned
from leo.acquisition.mixed_rate_schedule import (
    PRODUCTION_DIRECT_ASYNC_FIXED_25_HOLD_POLICY_V1,
    PRODUCTION_DIRECT_ASYNC_FIXED_25_HOLD_TAG_V1,
    PRODUCTION_DIRECT_ASYNC_HOLD_ROLLOUT_POLICY_V1,
    PRODUCTION_DIRECT_ASYNC_HOLD_ROLLOUT_TAG_V1,
)
from leo.cli.backend import (
    AcquisitionCliBackend,
    CliBackendError,
    ScheduledScannerBurst,
    ScheduledScannerConfiguration,
)
from leo.cli.models import CaptureDataV1, ExitCode, RunDataV2
from leo.cli.runner import ContinuousAcquisitionRunner
from leo.contracts.capture_control import (
    CaptureControlStateV1,
    CaptureDesiredState,
    CaptureObservedState,
)
from leo.contracts.gain_control import GainControllerMode
from leo.contracts.mixed_rate_schedule import (
    MIXED_RATE_SAFE_SCHEDULE_POLICY_V1,
    MIXED_RATE_SCHEDULE_POLICY_V1,
    PRODUCTION_2P5_10_15_RATE_POLICY_V2,
    PRODUCTION_DIRECT_ASYNC_RATE_POLICY_V3,
    PRODUCTION_NATIVE_RATE_POLICY_V2,
    ProductionDwellClass,
    ProductionDwellClassV2,
    ProductionDwellClassV3,
    ProductionDwellIntentV1,
    ProductionDwellIntentV2,
    ProductionDwellIntentV3,
)
from leo.contracts.states import CaptureState
from leo.scanner import ScannerBurstReportV1


class _Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


class _AdvancingCancel:
    def __init__(self, clock: _Clock, *, on_wait=None) -> None:
        self.clock = clock
        self.cancelled = False
        self.on_wait = on_wait

    def is_set(self) -> bool:
        return self.cancelled

    def wait(self, timeout: float) -> bool:
        self.clock.now += timeout
        if self.on_wait is not None:
            self.on_wait()
        return self.cancelled

    def set(self) -> None:
        self.cancelled = True


def _control(desired: CaptureDesiredState) -> CaptureControlStateV1:
    observed = (
        CaptureObservedState.RUNNING
        if desired is CaptureDesiredState.RUNNING
        else CaptureObservedState.PAUSED
    )
    return CaptureControlStateV1(
        generation=1,
        desired_state=desired,
        observed_state=observed,
        changed_utc_ns=1,
        operator_id="test",
        reason="test state",
    )


class _SupervisorBackend:
    def __init__(self, clock: _Clock) -> None:
        self.clock = clock
        self.control = _control(CaptureDesiredState.RUNNING)
        self.capture_times: list[float] = []
        self.scanner_capture_times: list[float] = []
        self.events: list[str] = []
        self.analyzed = Event()

    def reconcile_scanner_recordings(self) -> None:
        self.events.append("reconcile")

    def capture_control_snapshot(self) -> CaptureControlStateV1:
        return self.control

    def acquisition_queue_pressure(self) -> AcquisitionQueuePressure:
        return AcquisitionQueuePressure(queued=0, running=0)

    def scanner_schedule(self) -> ScheduledScannerConfiguration:
        return ScheduledScannerConfiguration(
            interval_seconds=5.0,
            maximum_lateness_seconds=1.0,
        )

    def capture_once(self, profile_name: str, **_kwargs) -> CaptureDataV1:
        self.capture_times.append(self.clock())
        self.events.append("dwell")
        return CaptureDataV1(
            session_id=f"capture-{len(self.capture_times)}",
            state=CaptureState.COMMITTED,
            radio_ids=("radio-a",),
            profile_name=profile_name,
            raw_iq_bytes=32,
            required_free_bytes=32,
            available_free_bytes=1024,
        )

    def capture_scheduled_scanner(self) -> ScheduledScannerBurst:
        self.scanner_capture_times.append(self.clock())
        self.events.append("scan")
        return cast(ScheduledScannerBurst, SimpleNamespace())

    def analyze_scheduled_scanner(self, _capture: ScheduledScannerBurst) -> ScannerBurstReportV1:
        assert self.analyzed.wait(timeout=2.0)
        return cast(
            ScannerBurstReportV1,
            SimpleNamespace(
                burst_id="burst-1",
                reports=(1, 2, 3, 4),
                active_edge_count=1,
            ),
        )


class _DurableSupervisorBackend(_SupervisorBackend):
    def __init__(self, clock: _Clock) -> None:
        super().__init__(clock)
        self.operations: list[SimpleNamespace] = []
        self.next_id = 1

    def enqueue_acquisition_operation(
        self,
        *,
        operation_key,
        kind,
        payload,
        scheduled_for,
        coalesce_pending_kind=False,
    ):
        existing = next(
            (item for item in self.operations if item.operation_key == operation_key),
            None,
        )
        if existing is not None:
            assert existing.kind == kind
            assert existing.payload == payload
            assert existing.scheduled_for == scheduled_for
            return existing
        if coalesce_pending_kind:
            for queued in self.operations:
                if queued.kind == kind and queued.state == "pending":
                    queued.state = "cancelled"
        item = SimpleNamespace(
            operation_id=self.next_id,
            operation_key=operation_key,
            kind=kind,
            payload=payload,
            scheduled_for=scheduled_for,
            state="pending",
            worker_id=None,
            attempt_count=0,
            outcome=None,
            error=None,
            retryable=None,
        )
        self.next_id += 1
        self.operations.append(item)
        return item

    def active_acquisition_operations(self, *, limit=200):
        active = tuple(item for item in self.operations if item.state in {"pending", "leased"})
        return active[:limit]

    def claim_acquisition_operation(self, *, worker_id, lease_for):
        if any(item.state == "leased" for item in self.operations):
            return None
        item = next((item for item in self.operations if item.state == "pending"), None)
        if item is None:
            return None
        item.state = "leased"
        item.worker_id = worker_id
        item.attempt_count += 1
        return SimpleNamespace(
            operation_id=item.operation_id,
            operation_key=item.operation_key,
            kind=item.kind,
            payload=item.payload,
            scheduled_for=item.scheduled_for,
        )

    def complete_acquisition_operation(self, *, operation_id, worker_id, outcome):
        item = next(item for item in self.operations if item.operation_id == operation_id)
        assert item.worker_id == worker_id
        item.state = "succeeded"
        item.worker_id = None
        item.outcome = outcome

    def fail_acquisition_operation(
        self,
        *,
        operation_id,
        worker_id,
        error,
        retryable,
        retry_after=timedelta(0),
    ):
        item = next(item for item in self.operations if item.operation_id == operation_id)
        item.state = "pending" if retryable else "failed"
        item.worker_id = None
        item.error = error
        item.retryable = retryable
        return item.state

    def reclaim_expired_acquisition_operations(self):
        return ()


class _MixedRateDurableBackend(_DurableSupervisorBackend):
    def mixed_rate_profile_authority(self) -> dict[int, tuple[str, str]]:
        return {
            2_500_000: ("rate-2p5", "sha256:" + "2" * 64),
            5_000_000: ("rate-5", "sha256:" + "5" * 64),
            15_000_000: ("rate-15", "sha256:" + "f" * 64),
        }

    def capture_mixed_once(
        self,
        intent: ProductionDwellIntentV1,
        **_kwargs,
    ) -> CaptureDataV1:
        return self.capture_once(
            intent.dwell_class.value,
            radio_ids=intent.radio_ids,
        )


class _ProductionRateDurableBackend(_DurableSupervisorBackend):
    def production_profile_authority(self):
        keys = (
            (2_500_000, (0, 1), False),
            (5_000_000, (0, 1), False),
            (2_500_000, (0, 1), True),
            (5_000_000, (0, 1), True),
            (10_000_000, (0,), True),
            (10_000_000, (1,), True),
            (15_000_000, (0,), True),
            (15_000_000, (1,), True),
            (20_000_000, (0,), True),
            (20_000_000, (1,), True),
            (25_000_000, (0,), True),
            (25_000_000, (1,), True),
        )
        return {
            key: (
                f"profile-{key[0]}-{'-'.join(map(str, key[1]))}-{int(key[2])}",
                f"sha256:{index:064x}",
                1_048_576,
            )
            for index, key in enumerate(keys, start=1)
        }

    def capture_production_once(
        self,
        intent: ProductionDwellIntentV2,
        **_kwargs,
    ) -> CaptureDataV1:
        return self.capture_once(intent.dwell_class.value, radio_ids=intent.radio_ids)


def test_durable_mixed_rate_policy_persists_exact_balanced_six_two_eight_cycle() -> None:
    clock = _Clock()
    backend = _MixedRateDurableBackend(clock)
    backend.analyzed.set()
    start = datetime.fromtimestamp(0, tz=UTC)
    profiles = ("ordinary-2p5", "ordinary-3", "ordinary-5")

    summary = ContinuousAcquisitionRunner(
        cast(AcquisitionCliBackend, backend),
        clock=clock,
        utc_now=lambda: start + timedelta(seconds=clock.now),
    ).run(
        profiles,
        radio_ids=("radio-a", "radio-b"),
        extra_tags=("production",),
        interval_seconds=10.0,
        maximum_captures=16,
        cancel=cast(Event, _AdvancingCancel(clock)),
        mixed_rate_policy=MIXED_RATE_SCHEDULE_POLICY_V1,
    )

    assert summary.capture_count == 16
    intents = tuple(
        ProductionDwellIntentV1.model_validate(item.payload)
        for item in backend.operations
        if item.kind == "scheduled_recording"
    )
    assert len(intents) == 16
    assert [intent.cadence_ordinal for intent in intents] == list(range(16))
    assert sum(intent.dwell_class is ProductionDwellClass.MIXED_2P5_5 for intent in intents) == 6
    assert sum(intent.dwell_class is ProductionDwellClass.MIXED_2P5_15 for intent in intents) == 2
    assert sum(intent.dwell_class is ProductionDwellClass.ORDINARY_POOL for intent in intents) == 8
    for dwell_class, high_rate in (
        (ProductionDwellClass.MIXED_2P5_5, 5_000_000),
        (ProductionDwellClass.MIXED_2P5_15, 15_000_000),
    ):
        high_radios = [
            next(item.radio_id for item in intent.radio_rates if item.sample_rate_hz == high_rate)
            for intent in intents
            if intent.dwell_class is dwell_class
        ]
        assert high_radios.count("radio-a") == high_radios.count("radio-b")


def test_durable_safe_policy_never_enqueues_unqualified_fifteen_m() -> None:
    clock = _Clock()
    backend = _MixedRateDurableBackend(clock)
    backend.analyzed.set()
    start = datetime.fromtimestamp(0, tz=UTC)

    summary = ContinuousAcquisitionRunner(
        cast(AcquisitionCliBackend, backend),
        clock=clock,
        utc_now=lambda: start + timedelta(seconds=clock.now),
    ).run(
        ("ordinary-2p5", "ordinary-3", "ordinary-5"),
        radio_ids=("radio-a", "radio-b"),
        extra_tags=("production",),
        interval_seconds=10.0,
        maximum_captures=16,
        cancel=cast(Event, _AdvancingCancel(clock)),
        mixed_rate_policy=MIXED_RATE_SAFE_SCHEDULE_POLICY_V1,
    )

    assert summary.capture_count == 16
    intents = tuple(
        ProductionDwellIntentV1.model_validate(item.payload)
        for item in backend.operations
        if item.kind == "scheduled_recording"
    )
    assert sum(item.dwell_class is ProductionDwellClass.MIXED_2P5_5 for item in intents) == 6
    assert sum(item.dwell_class is ProductionDwellClass.ORDINARY_POOL for item in intents) == 10
    assert all(rate.sample_rate_hz != 15_000_000 for item in intents for rate in item.radio_rates)


def test_durable_production_policy_executes_exact_eight_slot_bag() -> None:
    clock = _Clock()
    backend = _ProductionRateDurableBackend(clock)
    backend.analyzed.set()
    start = datetime.fromtimestamp(0, tz=UTC)

    summary = ContinuousAcquisitionRunner(
        cast(AcquisitionCliBackend, backend),
        clock=clock,
        utc_now=lambda: start + timedelta(seconds=clock.now),
    ).run(
        (
            "starlink-ch4-lower-2p5m-60s-native-bandwidth-v4",
            "starlink-ch4-lower-5m-60s-native-bandwidth-v4",
        ),
        radio_ids=("radio-a", "radio-b"),
        extra_tags=("production",),
        interval_seconds=10.0,
        maximum_captures=8,
        cancel=cast(Event, _AdvancingCancel(clock)),
        mixed_rate_policy=PRODUCTION_NATIVE_RATE_POLICY_V2,
    )

    assert summary.capture_count == 8
    intents = tuple(
        ProductionDwellIntentV2.model_validate(item.payload)
        for item in backend.operations
        if item.kind == "scheduled_recording"
    )
    assert len(intents) == 8
    assert {item.cadence_ordinal for item in intents} == set(range(8))
    observed = {dwell: 0 for dwell in ProductionDwellClassV2}
    for intent in intents:
        observed[intent.dwell_class] += 1
    assert observed == {
        ProductionDwellClassV2.BOTH_2P5: 2,
        ProductionDwellClassV2.BOTH_5: 2,
        ProductionDwellClassV2.MIXED_2P5_5: 1,
        ProductionDwellClassV2.MIXED_2P5_10: 1,
        ProductionDwellClassV2.MIXED_2P5_15: 1,
        ProductionDwellClassV2.MIXED_2P5_20: 1,
    }


def test_durable_focused_policy_executes_only_2p5_10_and_2p5_15_pairs() -> None:
    clock = _Clock()
    backend = _ProductionRateDurableBackend(clock)
    backend.analyzed.set()
    start = datetime.fromtimestamp(0, tz=UTC)

    summary = ContinuousAcquisitionRunner(
        cast(AcquisitionCliBackend, backend),
        clock=clock,
        utc_now=lambda: start + timedelta(seconds=clock.now),
    ).run(
        (
            "starlink-ch4-lower-2p5m-60s-native-bandwidth-v4",
            "starlink-ch4-lower-5m-60s-native-bandwidth-v4",
        ),
        radio_ids=("radio-a", "radio-b"),
        extra_tags=("production",),
        interval_seconds=10.0,
        maximum_captures=8,
        cancel=cast(Event, _AdvancingCancel(clock)),
        mixed_rate_policy=PRODUCTION_2P5_10_15_RATE_POLICY_V2,
    )

    assert summary.capture_count == 8
    intents = tuple(
        ProductionDwellIntentV2.model_validate(item.payload)
        for item in backend.operations
        if item.kind == "scheduled_recording"
    )
    assert len(intents) == 8
    assert {item.dwell_class for item in intents} == {
        ProductionDwellClassV2.MIXED_2P5_10,
        ProductionDwellClassV2.MIXED_2P5_15,
    }
    assert all(
        {leg.sample_rate_hz for leg in intent.radio_legs}
        in ({2_500_000, 10_000_000}, {2_500_000, 15_000_000})
        for intent in intents
    )


def test_durable_hold_rollout_enqueues_explicit_hold_v3_intents() -> None:
    clock = _Clock()
    backend = _ProductionRateDurableBackend(clock)
    backend.analyzed.set()
    start = datetime.fromtimestamp(0, tz=UTC)

    summary = ContinuousAcquisitionRunner(
        cast(AcquisitionCliBackend, backend),
        clock=clock,
        utc_now=lambda: start + timedelta(seconds=clock.now),
    ).run(
        (
            "starlink-ch4-lower-2p5m-60s-native-bandwidth-v4",
            "starlink-ch4-lower-5m-60s-native-bandwidth-v4",
        ),
        radio_ids=("radio-a", "radio-b"),
        extra_tags=("production",),
        interval_seconds=10.0,
        maximum_captures=6,
        cancel=cast(Event, _AdvancingCancel(clock)),
        mixed_rate_policy=PRODUCTION_DIRECT_ASYNC_HOLD_ROLLOUT_POLICY_V1,
    )

    assert summary.capture_count == 6
    intents = tuple(
        ProductionDwellIntentV3.model_validate(item.payload)
        for item in backend.operations
        if item.kind == "scheduled_recording"
    )
    assert len(intents) == 6
    assert all(item.policy_id == PRODUCTION_DIRECT_ASYNC_RATE_POLICY_V3 for item in intents)
    assert all(PRODUCTION_DIRECT_ASYNC_HOLD_ROLLOUT_TAG_V1 in item.extra_tags for item in intents)
    assert {leg.gain_controller.mode for intent in intents for leg in intent.radio_legs} == {
        GainControllerMode.TANDEM_HOLD
    }


def test_durable_fixed_25_selector_only_executes_2p5_x25_hold() -> None:
    clock = _Clock()
    backend = _ProductionRateDurableBackend(clock)
    backend.analyzed.set()
    start = datetime.fromtimestamp(0, tz=UTC)

    summary = ContinuousAcquisitionRunner(
        cast(AcquisitionCliBackend, backend),
        clock=clock,
        utc_now=lambda: start + timedelta(seconds=clock.now),
    ).run(
        (
            "starlink-ch4-lower-2p5m-60s-native-bandwidth-v4",
            "starlink-ch4-lower-5m-60s-native-bandwidth-v4",
        ),
        radio_ids=("radio-a", "radio-b"),
        extra_tags=("operator-fixed-rate",),
        interval_seconds=10.0,
        maximum_captures=6,
        cancel=cast(Event, _AdvancingCancel(clock)),
        mixed_rate_policy=PRODUCTION_DIRECT_ASYNC_FIXED_25_HOLD_POLICY_V1,
    )

    assert summary.capture_count == 6
    intents = tuple(
        ProductionDwellIntentV3.model_validate(item.payload)
        for item in backend.operations
        if item.kind == "scheduled_recording"
    )
    assert len(intents) == 6
    assert {intent.dwell_class for intent in intents} == {ProductionDwellClassV3.MIXED_2P5_25}
    assert all(
        PRODUCTION_DIRECT_ASYNC_FIXED_25_HOLD_TAG_V1 in intent.extra_tags for intent in intents
    )
    assert {leg.sample_rate_hz for intent in intents for leg in intent.radio_legs} == {
        2_500_000,
        25_000_000,
    }
    assert {leg.gain_controller.mode for intent in intents for leg in intent.radio_legs} == {
        GainControllerMode.TANDEM_HOLD
    }


def test_production_profile_revision_change_supersedes_same_slot_pending_intent() -> None:
    class MutableAuthorityBackend(_ProductionRateDurableBackend):
        authority_revision = "a"

        def production_profile_authority(self):
            authority = super().production_profile_authority()
            key = (25_000_000, (0,), True)
            profile, _revision, refill_samples = authority[key]
            authority[key] = (
                profile,
                "sha256:" + self.authority_revision * 64,
                refill_samples,
            )
            return authority

    clock = _Clock()
    backend = MutableAuthorityBackend(clock)
    backend.control = _control(CaptureDesiredState.PAUSED)
    start = datetime.fromtimestamp(0, tz=UTC)
    runner = ContinuousAcquisitionRunner(
        cast(AcquisitionCliBackend, backend),
        clock=clock,
        utc_now=lambda: start + timedelta(seconds=clock.now),
    )
    profiles = (
        "starlink-ch4-lower-2p5m-60s-native-bandwidth-v4",
        "starlink-ch4-lower-5m-60s-native-bandwidth-v4",
    )

    first_cancel = _AdvancingCancel(clock)
    first_cancel.on_wait = first_cancel.set
    runner.run(
        profiles,
        radio_ids=("radio-a", "radio-b"),
        extra_tags=("production",),
        interval_seconds=10.0,
        maximum_captures=None,
        cancel=cast(Event, first_cancel),
        mixed_rate_policy=PRODUCTION_DIRECT_ASYNC_HOLD_ROLLOUT_POLICY_V1,
    )
    backend.authority_revision = "b"
    second_cancel = _AdvancingCancel(clock)
    second_cancel.on_wait = second_cancel.set
    runner.run(
        profiles,
        radio_ids=("radio-a", "radio-b"),
        extra_tags=("production",),
        interval_seconds=10.0,
        maximum_captures=None,
        cancel=cast(Event, second_cancel),
        mixed_rate_policy=PRODUCTION_DIRECT_ASYNC_HOLD_ROLLOUT_POLICY_V1,
    )

    scheduled = [item for item in backend.operations if item.kind == "scheduled_recording"]
    assert len(scheduled) == 2
    assert scheduled[0].operation_key != scheduled[1].operation_key
    assert [item.state for item in scheduled] == ["cancelled", "pending"]


def test_supervisor_releases_scanner_path_for_ordinary_capture_during_analysis() -> None:
    clock = _Clock()
    backend = _SupervisorBackend(clock)

    original_capture = backend.capture_once

    def capture_and_release_analysis(profile_name: str, **kwargs) -> CaptureDataV1:
        result = original_capture(profile_name, **kwargs)
        if len(backend.capture_times) == 2:
            backend.analyzed.set()
        return result

    backend.capture_once = capture_and_release_analysis  # type: ignore[method-assign]
    summary = ContinuousAcquisitionRunner(
        cast(AcquisitionCliBackend, backend),
        clock=clock,
    ).run(
        "test-profile",
        radio_ids=("radio-a",),
        extra_tags=(),
        interval_seconds=10.0,
        maximum_captures=2,
        cancel=cast(Event, _AdvancingCancel(clock)),
    )

    assert summary.capture_count == 2
    assert backend.capture_times == [0.0, 10.0]
    assert backend.scanner_capture_times == [0.0]
    assert backend.events == ["reconcile", "dwell", "scan", "dwell"]


def test_supervisor_runs_one_scan_burst_after_each_eligible_dwell() -> None:
    clock = _Clock()
    backend = _SupervisorBackend(clock)
    backend.analyzed.set()
    analyses = 0

    def analyze(_capture: ScheduledScannerBurst) -> ScannerBurstReportV1:
        nonlocal analyses
        analyses += 1
        return cast(
            ScannerBurstReportV1,
            SimpleNamespace(
                burst_id=f"burst-{analyses}",
                reports=(1, 2, 3, 4),
                active_edge_count=0,
            ),
        )

    backend.analyze_scheduled_scanner = analyze  # type: ignore[method-assign]
    summary = ContinuousAcquisitionRunner(
        cast(AcquisitionCliBackend, backend),
        clock=clock,
    ).run(
        "test-profile",
        radio_ids=("radio-a",),
        extra_tags=(),
        interval_seconds=10.0,
        maximum_captures=3,
        cancel=cast(Event, _AdvancingCancel(clock)),
    )

    assert summary.capture_count == 3
    assert backend.events == ["reconcile", "dwell", "scan", "dwell", "scan", "dwell"]


def test_durable_supervisor_persists_and_alternates_dwell_scan_operations() -> None:
    clock = _Clock()
    backend = _DurableSupervisorBackend(clock)
    backend.analyzed.set()
    start = datetime(2026, 8, 21, 8, 0, tzinfo=UTC)

    summary = ContinuousAcquisitionRunner(
        cast(AcquisitionCliBackend, backend),
        clock=clock,
        utc_now=lambda: start + timedelta(seconds=clock.now),
    ).run(
        "test-profile",
        radio_ids=("radio-a",),
        extra_tags=(),
        interval_seconds=10.0,
        maximum_captures=3,
        cancel=cast(Event, _AdvancingCancel(clock)),
    )

    assert summary.capture_count == 3
    assert backend.events == ["reconcile", "dwell", "scan", "dwell", "scan", "dwell"]
    assert [item.kind for item in backend.operations] == [
        "scheduled_recording",
        "scanner_sweep",
        "scheduled_recording",
        "scanner_sweep",
        "scheduled_recording",
        "scanner_sweep",
    ]
    first_dwell = next(item for item in backend.operations if item.kind == "scheduled_recording")
    assert first_dwell.payload == {
        "profile_name": "test-profile",
        "radio_ids": ["radio-a"],
        "extra_tags": [],
    }


def test_durable_multi_profile_dwell_persists_one_selection_for_both_radios_and_retry() -> None:
    clock = _Clock()
    backend = _DurableSupervisorBackend(clock)
    backend.analyzed.set()
    start = datetime(2026, 8, 21, 8, 0, tzinfo=UTC)
    profile_names = (
        "starlink-ch4-lower-2p5m-60s-continuity-v2",
        "starlink-ch4-lower-3m-60s-capture-v2",
        "starlink-ch4-lower-5m-60s-segmented-v2",
    )
    selector_inputs: list[tuple[str, ...]] = []
    attempts: list[tuple[str, tuple[str, ...]]] = []
    original_capture = backend.capture_once

    def select(candidates: tuple[str, ...], _selection_key: str) -> str:
        selector_inputs.append(candidates)
        return candidates[1]

    def conflict_once(profile_name: str, **kwargs) -> CaptureDataV1:
        attempts.append((profile_name, tuple(kwargs["radio_ids"])))
        if len(attempts) == 1:
            raise CliBackendError("radios busy", ExitCode.CONFLICT)
        return original_capture(profile_name, **kwargs)

    backend.capture_once = conflict_once  # type: ignore[method-assign]
    summary = ContinuousAcquisitionRunner(
        cast(AcquisitionCliBackend, backend),
        clock=clock,
        utc_now=lambda: start + timedelta(seconds=clock.now),
        profile_selector=select,
    ).run(
        profile_names,
        radio_ids=("radio-a", "radio-b"),
        extra_tags=("campaign-a",),
        interval_seconds=10.0,
        maximum_captures=1,
        cancel=cast(Event, _AdvancingCancel(clock)),
    )

    assert isinstance(summary, RunDataV2)
    assert summary.profile_names == profile_names
    assert selector_inputs == [profile_names]
    assert attempts == [
        (profile_names[1], ("radio-a", "radio-b")),
        (profile_names[1], ("radio-a", "radio-b")),
    ]
    dwell = next(item for item in backend.operations if item.kind == "scheduled_recording")
    assert dwell.attempt_count == 2
    assert dwell.payload == {
        "schema_version": 1,
        "profile_name": profile_names[1],
        "profile_names": list(profile_names),
        "selection_policy": "uniform_per_dwell",
        "radio_ids": ["radio-a", "radio-b"],
        "extra_tags": ["campaign-a"],
    }


def test_durable_multi_profile_restart_reuses_the_persisted_selection() -> None:
    clock = _Clock()
    backend = _DurableSupervisorBackend(clock)
    start = datetime(2026, 8, 21, 8, 0, tzinfo=UTC)
    profile_names = (
        "starlink-ch4-lower-2p5m-60s-continuity-v2",
        "starlink-ch4-lower-3m-60s-capture-v2",
        "starlink-ch4-lower-5m-60s-segmented-v2",
    )
    backend.control = _control(CaptureDesiredState.PAUSED)
    first_cancel = _AdvancingCancel(clock)
    first_cancel.on_wait = first_cancel.set

    first_summary = ContinuousAcquisitionRunner(
        cast(AcquisitionCliBackend, backend),
        clock=clock,
        utc_now=lambda: start + timedelta(seconds=clock.now),
    ).run(
        profile_names,
        radio_ids=("radio-a", "radio-b"),
        extra_tags=(),
        interval_seconds=10.0,
        maximum_captures=1,
        cancel=cast(Event, first_cancel),
    )

    dwell = next(item for item in backend.operations if item.kind == "scheduled_recording")
    persisted_payload = dict(dwell.payload)
    backend.control = _control(CaptureDesiredState.RUNNING)
    second_summary = ContinuousAcquisitionRunner(
        cast(AcquisitionCliBackend, backend),
        clock=clock,
        utc_now=lambda: start + timedelta(seconds=clock.now),
    ).run(
        profile_names,
        radio_ids=("radio-a", "radio-b"),
        extra_tags=(),
        interval_seconds=10.0,
        maximum_captures=1,
        cancel=cast(Event, _AdvancingCancel(clock)),
    )

    dwells = [item for item in backend.operations if item.kind == "scheduled_recording"]
    assert first_summary.stopped_reason == "cancelled"
    assert second_summary.capture_count == 1
    assert len(dwells) == 1
    assert dwells[0].payload == persisted_payload
    assert second_summary.last_capture is not None
    assert second_summary.last_capture.profile_name == persisted_payload["profile_name"]


def test_backpressure_retains_due_dwell_until_admission_recovers() -> None:
    clock = _Clock()
    backend = _DurableSupervisorBackend(clock)
    observations = 0
    pending_seen = False

    def pressure() -> AcquisitionQueuePressure:
        nonlocal observations, pending_seen
        observations += 1
        pending_seen = pending_seen or any(
            item.kind == "scheduled_recording" and item.state == "pending"
            for item in backend.operations
        )
        return AcquisitionQueuePressure(queued=31 if observations == 1 else 0, running=0)

    backend.acquisition_queue_pressure = pressure  # type: ignore[method-assign]
    start = datetime(2026, 8, 21, 8, 0, tzinfo=UTC)
    summary = ContinuousAcquisitionRunner(
        cast(AcquisitionCliBackend, backend),
        clock=clock,
        utc_now=lambda: start + timedelta(seconds=clock.now),
    ).run(
        "test-profile",
        radio_ids=("radio-a",),
        extra_tags=(),
        interval_seconds=10.0,
        maximum_captures=1,
        cancel=cast(Event, _AdvancingCancel(clock)),
    )

    assert pending_seen
    assert observations >= 2
    assert summary.capture_count == 1
    assert backend.events == ["reconcile", "dwell"]


def test_durable_supervisor_coalesces_missed_cadence_slots() -> None:
    clock = _Clock()
    backend = _DurableSupervisorBackend(clock)
    backend.analyzed.set()
    start = datetime(2026, 8, 21, 8, 0, tzinfo=UTC)
    backend.control = _control(CaptureDesiredState.PAUSED)

    polls = 0

    def advance_while_paused() -> None:
        nonlocal polls
        polls += 1
        clock.now += 10.0
        if polls == 4:
            backend.control = _control(CaptureDesiredState.RUNNING)

    summary = ContinuousAcquisitionRunner(
        cast(AcquisitionCliBackend, backend),
        clock=clock,
        utc_now=lambda: start + timedelta(seconds=clock.now),
        capture_control_poll_seconds=0.25,
    ).run(
        "test-profile",
        radio_ids=("radio-a",),
        extra_tags=(),
        interval_seconds=10.0,
        maximum_captures=1,
        cancel=cast(Event, _AdvancingCancel(clock, on_wait=advance_while_paused)),
    )

    queued_dwells = [
        item
        for item in backend.operations
        if item.kind == "scheduled_recording" and item.state == "pending"
    ]
    assert summary.capture_count == 1
    assert len(queued_dwells) <= 1


def test_pause_fences_both_schedules_and_resume_starts_fresh_cadence() -> None:
    clock = _Clock()
    backend = _SupervisorBackend(clock)
    backend.control = _control(CaptureDesiredState.PAUSED)

    def resume_after_poll() -> None:
        backend.control = _control(CaptureDesiredState.RUNNING)

    cancel = _AdvancingCancel(clock, on_wait=resume_after_poll)
    summary = ContinuousAcquisitionRunner(
        cast(AcquisitionCliBackend, backend),
        clock=clock,
        capture_control_poll_seconds=0.25,
    ).run(
        "test-profile",
        radio_ids=("radio-a",),
        extra_tags=(),
        interval_seconds=10.0,
        maximum_captures=1,
        cancel=cast(Event, cancel),
    )

    assert summary.capture_count == 1
    assert backend.capture_times == [0.25]
    assert backend.scanner_capture_times == []


def test_durable_pause_preserves_due_operation_until_resume() -> None:
    clock = _Clock()
    backend = _DurableSupervisorBackend(clock)
    backend.control = _control(CaptureDesiredState.PAUSED)
    pending_while_paused = False

    def resume_after_observing_pending() -> None:
        nonlocal pending_while_paused
        pending_while_paused = any(
            item.kind == "scheduled_recording"
            and item.state == "pending"
            and item.attempt_count == 0
            for item in backend.operations
        )
        backend.control = _control(CaptureDesiredState.RUNNING)

    cancel = _AdvancingCancel(clock, on_wait=resume_after_observing_pending)
    start = datetime(2026, 8, 21, 8, 0, tzinfo=UTC)
    summary = ContinuousAcquisitionRunner(
        cast(AcquisitionCliBackend, backend),
        clock=clock,
        capture_control_poll_seconds=0.25,
        utc_now=lambda: start + timedelta(seconds=clock.now),
    ).run(
        "test-profile",
        radio_ids=("radio-a",),
        extra_tags=(),
        interval_seconds=10.0,
        maximum_captures=1,
        cancel=cast(Event, cancel),
    )

    assert pending_while_paused
    assert summary.capture_count == 1
    dwell = next(item for item in backend.operations if item.kind == "scheduled_recording")
    assert dwell.state == "succeeded"
    assert dwell.attempt_count == 1


@pytest.mark.parametrize(
    "capture_error",
    (
        "radio-a: refill queue full; capture cannot drain RF without blocking",
        (
            "radio-a: capture integrity degraded: gaps=1, missing_samples=262144, "
            "overflows=0, enqueue_failures=0, device_span=150000000/300000000"
        ),
        "radio-a: OSError: injected mid-read failure",
    ),
)
def test_durable_terminal_or_truncated_capture_preserves_evidence_but_fails_health_operation(
    capture_error: str,
) -> None:
    clock = _Clock()
    backend = _DurableSupervisorBackend(clock)
    start = datetime(2026, 8, 21, 8, 0, tzinfo=UTC)
    ordinary_capture = backend.capture_once

    def terminal_enqueue_failure(profile_name: str, **kwargs) -> CaptureDataV1:
        return ordinary_capture(profile_name, **kwargs).model_copy(
            update={
                "state": CaptureState.DEGRADED,
                "bundle_uri": "file:///bulk/recordings/degraded-capture",
                "manifest_sha256": "sha256:" + "a" * 64,
                "errors": (capture_error,),
            }
        )

    backend.capture_once = terminal_enqueue_failure  # type: ignore[method-assign]
    summary = ContinuousAcquisitionRunner(
        cast(AcquisitionCliBackend, backend),
        clock=clock,
        utc_now=lambda: start + timedelta(seconds=clock.now),
    ).run(
        "test-profile",
        radio_ids=("radio-a",),
        extra_tags=(),
        interval_seconds=10.0,
        maximum_captures=1,
        cancel=cast(Event, _AdvancingCancel(clock)),
    )

    assert summary.capture_count == 1
    assert summary.degraded_count == 1
    assert summary.last_capture is not None
    assert summary.last_capture.bundle_uri == "file:///bulk/recordings/degraded-capture"
    assert summary.last_capture.manifest_sha256 == "sha256:" + "a" * 64
    dwell = next(item for item in backend.operations if item.kind == "scheduled_recording")
    assert dwell.state == "failed"
    assert dwell.retryable is False
    assert "scheduled capture health rejected terminal or truncated evidence" in dwell.error
    assert capture_error in dwell.error
    assert not any(item.kind == "scanner_sweep" for item in backend.operations)


def test_durable_full_span_segmented_capture_remains_successful_and_scanner_eligible() -> None:
    clock = _Clock()
    backend = _DurableSupervisorBackend(clock)
    start = datetime(2026, 8, 21, 8, 0, tzinfo=UTC)
    ordinary_capture = backend.capture_once

    def full_span_segmented(profile_name: str, **kwargs) -> CaptureDataV1:
        return ordinary_capture(profile_name, **kwargs).model_copy(
            update={
                "state": CaptureState.DEGRADED,
                "bundle_uri": "file:///bulk/recordings/full-span-segmented",
                "manifest_sha256": "sha256:" + "b" * 64,
                "errors": (
                    "radio-a: capture integrity degraded: gaps=66, "
                    "missing_samples=17146624, overflows=0, enqueue_failures=0, "
                    "device_span=300000000/300000000",
                ),
            }
        )

    backend.capture_once = full_span_segmented  # type: ignore[method-assign]
    summary = ContinuousAcquisitionRunner(
        cast(AcquisitionCliBackend, backend),
        clock=clock,
        utc_now=lambda: start + timedelta(seconds=clock.now),
    ).run(
        "test-profile",
        radio_ids=("radio-a",),
        extra_tags=(),
        interval_seconds=10.0,
        maximum_captures=1,
        cancel=cast(Event, _AdvancingCancel(clock)),
    )

    assert summary.capture_count == 1
    assert summary.degraded_count == 1
    dwell = next(item for item in backend.operations if item.kind == "scheduled_recording")
    assert dwell.state == "succeeded"
    assert dwell.outcome == "capture capture-1 degraded"
    scanner = next(item for item in backend.operations if item.kind == "scanner_sweep")
    assert scanner.state == "pending"


def test_durable_poisoned_supervisor_fails_operation_and_terminates_before_next_dwell() -> None:
    clock = _Clock()
    backend = _DurableSupervisorBackend(clock)
    start = datetime(2026, 8, 21, 8, 0, tzinfo=UTC)
    release_consumer = Event()
    consumer = Thread(target=release_consumer.wait, name="timed-out-writer", daemon=True)
    consumer.start()
    attempts = 0

    def poisoned_capture(_profile_name: str, **_kwargs) -> CaptureDataV1:
        nonlocal attempts
        attempts += 1
        raise AcquisitionSupervisorPoisoned(
            session_id="poisoned-capture",
            consumer_threads=(consumer,),
            errors=("storage consumer did not stop before bounded timeout",),
        )

    backend.capture_once = poisoned_capture  # type: ignore[assignment]
    try:
        with pytest.raises(AcquisitionSupervisorPoisoned, match="supervisor is poisoned"):
            ContinuousAcquisitionRunner(
                cast(AcquisitionCliBackend, backend),
                clock=clock,
                utc_now=lambda: start + timedelta(seconds=clock.now),
            ).run(
                "test-profile",
                radio_ids=("radio-a",),
                extra_tags=(),
                interval_seconds=0.0,
                maximum_captures=2,
                cancel=cast(Event, _AdvancingCancel(clock)),
            )
    finally:
        release_consumer.set()
        consumer.join(timeout=1.0)

    assert attempts == 1
    dwells = [item for item in backend.operations if item.kind == "scheduled_recording"]
    assert len(dwells) == 1
    assert dwells[0].state == "failed"
    assert dwells[0].retryable is False
    assert "AcquisitionSupervisorPoisoned" in dwells[0].error
    assert "bounded timeout" in dwells[0].error
    assert not any(item.kind == "scanner_sweep" for item in backend.operations)
