from __future__ import annotations

import threading
from collections.abc import Mapping
from decimal import Decimal
from pathlib import Path
from threading import Event
from typing import Any

import numpy as np
import pytest

from leo.acquisition import (
    AcquisitionConfig,
    AcquisitionCoordinator,
    StorageAdmissionDecision,
)
from leo.contracts.profile import CapturePlanV1, CaptureProfileRevisionV1, CaptureProfileV1
from leo.contracts.radio import RadioSettingsV1, ReceiverGainV1
from leo.contracts.recording import CompressionSettingsV1, HostIdentityV1, ProducerV1
from leo.contracts.states import (
    CaptureState,
    ContinuityPolicy,
    ContinuityStatus,
    GainMode,
    PeerFailurePolicy,
    SourceType,
    StreamState,
    SynchronizationGrade,
    TimingMethod,
)
from leo.domain.iq import IqBlock
from leo.domain.profiles import compile_capture_plan
from leo.radio import FakeRadioSource
from leo.storage import RecordingStore


class ImmediateClock:
    def __init__(self) -> None:
        self.waited_targets: list[int] = []
        self._lock = threading.Lock()

    def utc_ns(self) -> int:
        return 1_800_000_000_000_000_000

    def monotonic_ns(self) -> int:
        return 4_000_000_000

    def sleep(self, seconds: float, cancel: Event) -> None:
        if cancel.is_set():
            raise RuntimeError("cancelled")

    def wait_until(self, target_monotonic_ns: int, cancel: Event) -> int:
        if cancel.is_set():
            raise RuntimeError("cancelled")
        with self._lock:
            self.waited_targets.append(target_monotonic_ns)
        return target_monotonic_ns + 100


class PhaseBarrierRadio(FakeRadioSource):
    def __init__(
        self,
        radio_id: str,
        barriers: Mapping[str, threading.Barrier],
        **kwargs: Any,
    ) -> None:
        super().__init__(radio_id, **kwargs)
        self._barriers = barriers
        self._reads = 0

    def open(self):
        self._barriers["open"].wait(timeout=2)
        return super().open()

    def configure(self, settings):
        self._barriers["configure"].wait(timeout=2)
        return super().configure(settings)

    def read_block(self, sample_count: int) -> IqBlock:
        if self._reads == 0:
            self._barriers["prime"].wait(timeout=2)
        self._reads += 1
        return super().read_block(sample_count)


class CancelAfterFirstBlockRadio(FakeRadioSource):
    def __init__(self, radio_id: str, cancel: Event) -> None:
        super().__init__(radio_id)
        self._cancel = cancel
        self._reads = 0

    def read_block(self, sample_count: int) -> IqBlock:
        block = super().read_block(sample_count)
        self._reads += 1
        if self._reads == 1:
            self._cancel.set()
        return block


class OpenObservedRadio(FakeRadioSource):
    def __init__(self, radio_id: str) -> None:
        super().__init__(radio_id)
        self.opened = False

    def open(self):
        self.opened = True
        return super().open()


class ConfigureFailureRadio(FakeRadioSource):
    def configure(self, settings):
        raise RuntimeError("injected configuration failure")


class DelayedHostBracketRadio(FakeRadioSource):
    """Model a Pluto whose second refill is delayed without device counters."""

    def read_block(self, sample_count: int) -> IqBlock:
        block = super().read_block(sample_count)
        delay_ns = block.metadata.session_sample_start // sample_count * 10_000_000_000
        interval = block.metadata.host_request_utc_ns.model_copy(
            update={
                "lower_ns": block.metadata.host_request_utc_ns.lower_ns + delay_ns,
                "upper_ns": block.metadata.host_request_utc_ns.upper_ns + delay_ns,
            }
        )
        metadata = block.metadata.model_copy(
            update={
                "host_request_utc_ns": interval,
                "timing_method": TimingMethod.HOST_BRACKET,
                "device_sample_counter": None,
                "source_sequence": None,
                "continuity": ContinuityStatus.UNKNOWN,
            }
        )
        return IqBlock(samples=block.samples, metadata=metadata)


def _plan(
    radio_ids: tuple[str, ...] = ("radio-a",),
    *,
    sample_count: int = 12,
    sample_rate_hz: int = 2_500_000,
    refill_samples: int = 4,
    prime_refills: int = 0,
    continuity_policy: ContinuityPolicy = ContinuityPolicy.REQUIRE_CONTIGUOUS,
    peer_failure_policy: PeerFailurePolicy = PeerFailurePolicy.KEEP_SURVIVOR,
) -> CapturePlanV1:
    profile = CaptureProfileV1(
        name="acquisition-test",
        center_frequency_hz=1_700_000_000,
        sample_rate_hz=sample_rate_hz,
        bandwidth_hz=2_500_000,
        receivers=(0, 1),
        gain_mode=GainMode.MANUAL,
        gains=(
            ReceiverGainV1(receiver_id=0, gain_db=30.0),
            ReceiverGainV1(receiver_id=1, gain_db=30.0),
        ),
        sample_count=sample_count,
        refill_samples=refill_samples,
        settle_seconds=Decimal(0),
        prime_refills=prime_refills,
        continuity_policy=continuity_policy,
        peer_failure_policy=peer_failure_policy,
        storage_policy="test-zstd-v1",
        tags=("TEST",),
    )
    return compile_capture_plan(
        CaptureProfileRevisionV1.from_profile(profile),
        radio_ids,
        source_type=SourceType.TEST,
    )


def _coordinator(
    tmp_path: Path,
    *,
    clock: ImmediateClock | None = None,
    free_bytes=lambda _path: 10**12,
    storage_admission=lambda _path: StorageAdmissionDecision(allowed=True),
) -> AcquisitionCoordinator:
    return AcquisitionCoordinator(
        RecordingStore(tmp_path / "bulk"),
        compression=CompressionSettingsV1(
            policy_id="test-zstd-v1",
            target_uncompressed_bytes=48,
        ),
        clock=clock or ImmediateClock(),
        config=AcquisitionConfig(
            release_lead_ns=25_000_000,
            readiness_timeout_seconds=2,
            safety_reserve_bytes=1024,
            metadata_bytes_per_refill=128,
        ),
        free_bytes=free_bytes,
        storage_admission=storage_admission,
        host=HostIdentityV1(hostname="acquisition-test-host"),
        producer=ProducerV1(name="acquisition-test", version="1"),
    )


def test_single_radio_capture_is_bounded_published_and_exact(tmp_path: Path) -> None:
    coordinator = _coordinator(tmp_path)
    plan = _plan(sample_count=10, refill_samples=4)
    radio = FakeRadioSource("radio-a", seed=17)

    result = coordinator.capture_once(
        plan,
        {"radio-a": radio},
        session_id="single-complete",
    )

    assert result.state is CaptureState.COMMITTED
    assert result.bundle is not None
    assert result.manifest is not None
    stream = result.manifest.streams[0]
    assert stream.state is StreamState.COMPLETE
    assert stream.captured_sample_count == 10
    assert stream.continuity.refill_count == 3
    assert result.manifest.synchronization.grade is SynchronizationGrade.NOT_REQUESTED
    readback = coordinator.store.read_ci16(result.bundle, "stream-0", 0, 10)
    assert readback.shape == (10, 2, 2)
    assert readback.dtype == np.dtype("<i2")
    coordinator.store.verify(result.bundle)


def test_paired_capture_persists_independent_gain_modes_and_tuning(tmp_path: Path) -> None:
    coordinator = _coordinator(tmp_path)
    plan = _plan(("radio-a", "radio-b"), sample_count=4)
    base = plan.profile_revision.profile
    settings = {
        "radio-a": RadioSettingsV1(
            center_frequency_hz=959_687_500,
            sample_rate_hz=base.sample_rate_hz,
            bandwidth_hz=base.bandwidth_hz,
            receiver_ids=base.receivers,
            gain_mode=base.gain_mode,
            gains=base.gains,
        ),
        "radio-b": RadioSettingsV1(
            center_frequency_hz=1_940_312_500,
            sample_rate_hz=base.sample_rate_hz,
            bandwidth_hz=base.bandwidth_hz,
            receiver_ids=base.receivers,
            gain_mode=GainMode.SLOW_ATTACK,
            gains=(),
        ),
    }

    result = coordinator.capture_once(
        plan,
        {"radio-a": FakeRadioSource("radio-a"), "radio-b": FakeRadioSource("radio-b")},
        session_id="paired-per-radio-tuning",
        requested_settings_by_radio=settings,
        extra_tags=(
            "gain_mode:stream-0:manual",
            "gain_mode:stream-1:slow_attack",
            "tuning_policy:independent",
            "tuning:stream-0:ch1:lower",
            "tuning:stream-1:ch4:upper",
        ),
    )

    assert result.manifest is not None
    assert tuple(
        stream.requested_settings.center_frequency_hz for stream in result.manifest.streams
    ) == (959_687_500, 1_940_312_500)
    assert tuple(stream.requested_settings.gain_mode for stream in result.manifest.streams) == (
        GainMode.MANUAL,
        GainMode.SLOW_ATTACK,
    )
    assert result.manifest.tags == (
        "TEST",
        "gain_mode:stream-0:manual",
        "gain_mode:stream-1:slow_attack",
        "tuning:stream-0:ch1:lower",
        "tuning:stream-1:ch4:upper",
        "tuning_policy:independent",
    )


def test_per_radio_settings_still_reject_capture_geometry_changes(tmp_path: Path) -> None:
    coordinator = _coordinator(tmp_path)
    plan = _plan(("radio-a", "radio-b"), sample_count=4)
    base = plan.profile_revision.profile
    settings = {
        radio_id: RadioSettingsV1(
            center_frequency_hz=base.center_frequency_hz,
            sample_rate_hz=base.sample_rate_hz + (1 if radio_id == "radio-b" else 0),
            bandwidth_hz=base.bandwidth_hz,
            receiver_ids=base.receivers,
            gain_mode=base.gain_mode,
            gains=base.gains,
        )
        for radio_id in plan.radio_ids
    }

    with pytest.raises(ValueError, match="center frequency and gain configuration"):
        coordinator.capture_once(
            plan,
            {"radio-a": FakeRadioSource("radio-a"), "radio-b": FakeRadioSource("radio-b")},
            session_id="invalid-per-radio-geometry",
            requested_settings_by_radio=settings,
        )


@pytest.mark.parametrize(
    ("used_fraction", "warning", "allowed"),
    [
        (0.70, False, True),
        (0.75, True, True),
        (0.80, True, False),
    ],
)
def test_catalog_retention_watermarks_drive_orm_free_capture_admission(
    tmp_path: Path,
    used_fraction: float,
    warning: bool,
    allowed: bool,
) -> None:
    radio = OpenObservedRadio("radio-a")
    decision = StorageAdmissionDecision(
        allowed=allowed,
        used_fraction=used_fraction,
        warning=warning,
        reason="retention blocked" if not allowed else None,
    )
    result = _coordinator(
        tmp_path,
        storage_admission=lambda _path: decision,
    ).capture_once(
        _plan(),
        {"radio-a": radio},
        session_id=f"admission-{round(used_fraction * 100)}",
    )

    assert result.admission.storage_used_fraction == used_fraction
    assert result.admission.storage_warning is warning
    assert result.admission.admitted is allowed
    assert radio.opened is allowed
    if allowed:
        assert result.state is CaptureState.COMMITTED
    else:
        assert result.state is CaptureState.FAILED
        assert any("retention blocked" in error for error in result.errors)


def test_dual_prepare_phases_are_concurrent_and_release_target_is_common(
    tmp_path: Path,
) -> None:
    barriers = {name: threading.Barrier(2) for name in ("open", "configure", "prime")}
    radio_a = PhaseBarrierRadio(
        "radio-a",
        barriers,
        utc_origin_ns=1_700_000_000_000_000_000,
    )
    radio_b = PhaseBarrierRadio(
        "radio-b",
        barriers,
        utc_origin_ns=1_700_000_000_002_000_000,
    )
    clock = ImmediateClock()
    coordinator = _coordinator(tmp_path, clock=clock)

    result = coordinator.capture_once(
        _plan(("radio-a", "radio-b"), sample_count=8, prime_refills=1),
        {"radio-a": radio_a, "radio-b": radio_b},
        session_id="paired-complete",
    )

    assert result.state is CaptureState.COMMITTED
    assert result.manifest is not None
    timing_targets = {
        stream.timing.release_target_monotonic_ns
        for stream in result.manifest.streams
        if stream.timing is not None
    }
    assert timing_targets == {4_025_000_000}
    assert clock.waited_targets.count(4_025_000_000) == 2
    sync = result.manifest.synchronization
    assert sync.grade is SynchronizationGrade.BEST_EFFORT_OBSERVED
    assert sync.estimated_start_skew_ns == 2_000_000
    assert sync.start_skew_uncertainty_ns == 2_000_000
    assert sync.estimated_overlap_ns is not None
    assert sync.guaranteed_overlap_ns is not None
    assert sync.phase_coherent is False


def test_host_only_delayed_reads_never_inflate_signal_overlap(tmp_path: Path) -> None:
    sample_count = 1_000
    plan = _plan(("radio-a", "radio-b"), sample_count=sample_count, refill_samples=500)
    result = _coordinator(tmp_path).capture_once(
        plan,
        {
            "radio-a": DelayedHostBracketRadio("radio-a"),
            "radio-b": DelayedHostBracketRadio("radio-b"),
        },
        session_id="host-lag-pair",
    )

    assert result.manifest is not None
    maximum_signal_duration_ns = sample_count * 1_000_000_000 // 2_500_000
    sync = result.manifest.synchronization
    assert sync.estimated_overlap_ns is not None
    assert sync.estimated_overlap_ns <= maximum_signal_duration_ns
    assert sync.guaranteed_overlap_ns == 0
    assert sync.grade is SynchronizationGrade.DEGRADED
    for stream in result.manifest.streams:
        assert stream.continuity.sample_loss_observable is False
        assert stream.timing is not None
        last = stream.timing.last_sample
        assert last.latest_utc_ns - last.estimate_utc_ns > 9_000_000_000


def test_keep_survivor_publishes_truthful_degraded_pair(tmp_path: Path) -> None:
    coordinator = _coordinator(tmp_path)
    result = coordinator.capture_once(
        _plan(("radio-a", "radio-b"), sample_count=8),
        {
            "radio-a": FakeRadioSource("radio-a"),
            "radio-b": FakeRadioSource("radio-b", fail_after_blocks=0),
        },
        session_id="paired-survivor",
    )

    assert result.state is CaptureState.DEGRADED
    assert result.bundle is not None
    assert result.manifest is not None
    assert tuple(stream.state for stream in result.manifest.streams) == (
        StreamState.COMPLETE,
        StreamState.FAILED,
    )
    assert result.manifest.synchronization.grade is SynchronizationGrade.DEGRADED
    assert result.manifest.synchronization.estimated_start_skew_ns is None
    coordinator.store.verify(result.bundle)


def test_preconfiguration_peer_failure_retains_intent_without_fake_readback(
    tmp_path: Path,
) -> None:
    coordinator = _coordinator(tmp_path)
    plan = _plan(("radio-a", "radio-b"), sample_count=8)
    result = coordinator.capture_once(
        plan,
        {
            "radio-a": FakeRadioSource("radio-a"),
            "radio-b": ConfigureFailureRadio("radio-b"),
        },
        session_id="paired-config-failure",
    )

    assert result.state is CaptureState.DEGRADED
    assert result.manifest is not None
    assert result.bundle is not None
    failed = result.manifest.streams[1]
    assert failed.state is StreamState.FAILED
    assert failed.requested_settings.receiver_ids == (0, 1)
    assert failed.requested_settings.sample_rate_hz == 2_500_000
    assert failed.applied_settings is None
    coordinator.store.verify(result.bundle)


def test_fail_session_policy_does_not_publish_a_survivor(tmp_path: Path) -> None:
    coordinator = _coordinator(tmp_path)
    result = coordinator.capture_once(
        _plan(
            ("radio-a", "radio-b"),
            sample_count=8,
            peer_failure_policy=PeerFailurePolicy.FAIL_SESSION,
        ),
        {
            "radio-a": FakeRadioSource("radio-a"),
            "radio-b": FakeRadioSource("radio-b", fail_after_blocks=0),
        },
        session_id="paired-fail-whole",
    )

    assert result.state is CaptureState.FAILED
    assert result.bundle is None
    assert not coordinator.store.reconcile().committed
    assert any("peer-failure policy" in error for error in result.errors)


def test_required_continuity_stops_before_gap_and_publishes_partial(tmp_path: Path) -> None:
    coordinator = _coordinator(tmp_path)
    result = coordinator.capture_once(
        _plan(sample_count=12, refill_samples=4),
        {"radio-a": FakeRadioSource("radio-a", gaps_before_blocks={1: 3})},
        session_id="gap-rejected",
    )

    assert result.state is CaptureState.DEGRADED
    assert result.manifest is not None
    stream = result.manifest.streams[0]
    assert stream.state is StreamState.PARTIAL
    assert stream.captured_sample_count == 4
    assert "gap_before" in (stream.error or "")
    assert stream.continuity.gap_count == 0


def test_segmented_continuity_preserves_gap_evidence(tmp_path: Path) -> None:
    coordinator = _coordinator(tmp_path)
    result = coordinator.capture_once(
        _plan(
            sample_count=12,
            refill_samples=4,
            continuity_policy=ContinuityPolicy.ALLOW_SEGMENTS,
        ),
        {"radio-a": FakeRadioSource("radio-a", gaps_before_blocks={1: 3})},
        session_id="gap-segmented",
    )

    assert result.state is CaptureState.COMMITTED
    assert result.manifest is not None
    stream = result.manifest.streams[0]
    assert stream.continuity.gap_count == 1
    assert stream.continuity.missing_sample_count == 3
    assert stream.continuity.segment_count == 2


def test_cancellation_keeps_partial_spool_unpublished(tmp_path: Path) -> None:
    cancel = Event()
    coordinator = _coordinator(tmp_path)
    result = coordinator.capture_once(
        _plan(sample_count=12, refill_samples=4),
        {"radio-a": CancelAfterFirstBlockRadio("radio-a", cancel)},
        session_id="cancelled-capture",
        cancel=cancel,
    )

    assert result.state is CaptureState.FAILED
    assert result.bundle is None
    assert not coordinator.store.reconcile().committed
    assert (coordinator.store.spool_root / "cancelled-capture.partial").is_dir()
    assert any("cancelled" in error for error in result.errors)


def test_admission_rejection_occurs_before_radio_open(tmp_path: Path) -> None:
    radio = OpenObservedRadio("radio-a")
    coordinator = _coordinator(tmp_path, free_bytes=lambda _path: 0)

    result = coordinator.capture_once(
        _plan(),
        {"radio-a": radio},
        session_id="no-space",
    )

    assert result.state is CaptureState.FAILED
    assert not result.admission.admitted
    assert not radio.opened
    assert not coordinator.store.spool_root.joinpath("no-space.partial").exists()


@pytest.mark.parametrize(
    ("sample_rate_hz", "sample_count", "raw_bytes", "metadata_bytes"),
    (
        (3_000_000, 180_000_000, 2_880_000_000, 5_627_904),
        (5_000_000, 300_000_000, 4_800_000_000, 9_379_840),
    ),
)
def test_dual_radio_rate_mode_admission_geometry_is_exact(
    tmp_path: Path,
    sample_rate_hz: int,
    sample_count: int,
    raw_bytes: int,
    metadata_bytes: int,
) -> None:
    coordinator = AcquisitionCoordinator(
        RecordingStore(tmp_path / "bulk-rate-admission"),
        config=AcquisitionConfig(
            safety_reserve_bytes=0,
            metadata_bytes_per_refill=4_096,
        ),
        free_bytes=lambda _path: 10**12,
    )
    plan = _plan(
        ("radio-a", "radio-b"),
        sample_count=sample_count,
        sample_rate_hz=sample_rate_hz,
        refill_samples=262_144,
    )

    admission = coordinator.estimate_admission(plan)

    assert admission.raw_iq_bytes == raw_bytes
    assert admission.metadata_reserve_bytes == metadata_bytes
    assert admission.required_free_bytes == raw_bytes + metadata_bytes
    assert admission.admitted is True


def test_source_mapping_must_match_compiled_plan(tmp_path: Path) -> None:
    coordinator = _coordinator(tmp_path)
    result = coordinator.capture_once(
        _plan(),
        {"wrong-radio": FakeRadioSource("wrong-radio")},
        session_id="mapping-mismatch",
    )

    assert result.state is CaptureState.FAILED
    assert any("mapping mismatch" in error for error in result.errors)
