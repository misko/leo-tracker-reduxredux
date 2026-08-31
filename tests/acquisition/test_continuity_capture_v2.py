from __future__ import annotations

import logging
import queue
import threading
import time
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path
from threading import Event

import numpy as np
import pytest

import leo.acquisition.coordinator as acquisition_coordinator
from leo.acquisition import (
    AcquisitionApplication,
    AcquisitionConfig,
    AcquisitionCoordinator,
    AcquisitionSupervisorPoisoned,
    AuthorizedAcquisitionApplication,
    CaptureTaskKind,
    LocalCaptureAuthority,
    RadioBusyError,
    RadioResource,
)
from leo.acquisition.mixed_rate_schedule import compile_production_dwell_intent_v2
from leo.contracts.device_buffer import DIRECT_ASYNC_EVIDENCE_KEY_V1, DirectAsyncEvidenceV1
from leo.contracts.mixed_rate_schedule import ProductionDwellClass, ProductionDwellClassV2
from leo.contracts.profile import (
    CaptureProfileRevisionV1,
    CaptureProfileRevisionV2,
    CaptureProfileV1,
    CaptureProfileV2,
)
from leo.contracts.radio import RadioSettingsV1, ReceiverGainV1
from leo.contracts.recording import (
    DEVICE_AXIS_STORAGE_POLICY_V1,
    CompressionSettingsV1,
    ContinuitySummaryV2,
    RecordingManifestV2,
    RecordingManifestV3,
    RecordingManifestV4,
    RecordingManifestV5,
)
from leo.contracts.states import (
    CaptureState,
    ContinuityPolicy,
    GainMode,
    PeerFailurePolicy,
    SourceType,
    StarlinkEdge,
    StreamState,
    TimingMethod,
)
from leo.domain.iq import IqBlock
from leo.domain.mixed_rate_capture import (
    compile_mixed_rate_capture_plan_v3,
    compile_production_capture_plan_v4,
)
from leo.domain.profiles import compile_capture_plan
from leo.processing.continuity import iter_masked_device_iq
from leo.radio.fake import FakeRadioSource
from leo.storage import RecordingStore
from leo.storage import writer as storage_writer
from leo.storage.writer import (
    DeviceAxisStreamBundleWriter,
    RecordingBundleWriter,
    StreamBundleWriter,
)


def _plan(
    *,
    radio_ids: tuple[str, ...] = ("radio-a",),
    sample_count: int = 12,
    sample_rate_hz: int = 2_500_000,
    refill_samples: int = 4,
    queue_capacity: int = 32,
    source_type: SourceType = SourceType.LIVE,
    continuity_policy: ContinuityPolicy = ContinuityPolicy.ALLOW_SEGMENTS,
):
    profile = CaptureProfileV2(
        name="continuity-v2-test",
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
        prime_refills=0,
        kernel_buffers=8,
        refill_queue_capacity=queue_capacity,
        continuity_policy=continuity_policy,
        storage_policy="test-zstd-v1",
        tags=("LIVE",),
    )
    return compile_capture_plan(
        CaptureProfileRevisionV2.from_profile(profile),
        radio_ids,
        source_type=source_type,
    )


def _coordinator(tmp_path: Path) -> AcquisitionCoordinator:
    return AcquisitionCoordinator(
        RecordingStore(tmp_path / "bulk"),
        compression=CompressionSettingsV1(
            policy_id="test-zstd-v1",
            target_uncompressed_bytes=1024,
        ),
        config=AcquisitionConfig(safety_reserve_bytes=0),
        free_bytes=lambda _path: 10**12,
    )


def _device_axis_plan(
    *,
    radio_ids: tuple[str, ...] = ("radio-a",),
    sample_count: int = 12,
    sample_rate_hz: int = 2_500_000,
    refill_samples: int = 4,
    queue_capacity: int = 32,
    native_bandwidth: bool = False,
):
    base = _plan(
        radio_ids=radio_ids,
        sample_count=sample_count,
        sample_rate_hz=sample_rate_hz,
        refill_samples=refill_samples,
        queue_capacity=queue_capacity,
    ).profile_revision.profile
    profile = base.model_copy(
        update={
            "name": "continuity-device-axis-v3-test",
            "storage_policy": DEVICE_AXIS_STORAGE_POLICY_V1,
            "peer_failure_policy": PeerFailurePolicy.FAIL_SESSION,
            "tags": (
                "CAPTURE_ONLY",
                "DEVICE_AXIS_ZERO_FILL",
                "LIVE",
                *(("NATIVE_BANDWIDTH",) if native_bandwidth else ()),
            ),
        }
    )
    return compile_capture_plan(
        CaptureProfileRevisionV2.from_profile(profile),
        radio_ids,
        source_type=SourceType.LIVE,
    )


def _device_axis_coordinator(tmp_path: Path) -> AcquisitionCoordinator:
    return AcquisitionCoordinator(
        RecordingStore(tmp_path / "bulk"),
        compression=CompressionSettingsV1(
            policy_id=DEVICE_AXIS_STORAGE_POLICY_V1,
            target_uncompressed_bytes=64,
        ),
        config=AcquisitionConfig(safety_reserve_bytes=0),
        free_bytes=lambda _path: 10**12,
    )


def _direct_async_plan():
    frame_samples = 1_048_576
    profile = CaptureProfileV2(
        name="direct-async-segment-test",
        center_frequency_hz=1_700_000_000,
        sample_rate_hz=10_000_000,
        bandwidth_hz=10_000_000,
        receivers=(0,),
        gain_mode=GainMode.MANUAL,
        gains=(ReceiverGainV1(receiver_id=0, gain_db=30.0),),
        sample_count=64 * frame_samples + 1,
        refill_samples=frame_samples,
        settle_seconds=Decimal(0),
        prime_refills=0,
        kernel_buffers=15,
        refill_queue_capacity=64,
        continuity_policy=ContinuityPolicy.ALLOW_SEGMENTS,
        synchronization_mode="best_effort",
        peer_failure_policy=PeerFailurePolicy.FAIL_SESSION,
        storage_policy=DEVICE_AXIS_STORAGE_POLICY_V1,
        tags=(
            "CAPTURE_ONLY",
            "DEVICE_AXIS_ZERO_FILL",
            "DEVICE_BUFFER:DIRECT_ASYNC_SEGMENTED_V1",
            "LIVE",
            "NATIVE_BANDWIDTH",
        ),
    )
    return compile_capture_plan(
        CaptureProfileRevisionV2.from_profile(profile),
        ("radio-a",),
        source_type=SourceType.LIVE,
    )


def _mixed_rate_plan(high_rate_hz: int):
    duration = Decimal("0.000004")

    def revision(rate_hz: int) -> CaptureProfileRevisionV2:
        return CaptureProfileRevisionV2.from_profile(
            CaptureProfileV2(
                name=f"mixed-{rate_hz}-test",
                center_frequency_hz=1_700_000_000,
                sample_rate_hz=rate_hz,
                bandwidth_hz=rate_hz,
                receivers=(0, 1),
                gain_mode=GainMode.MANUAL,
                gains=(
                    ReceiverGainV1(receiver_id=0, gain_db=30.0),
                    ReceiverGainV1(receiver_id=1, gain_db=30.0),
                ),
                duration_seconds=duration,
                refill_samples=4,
                settle_seconds=Decimal(0),
                prime_refills=0,
                kernel_buffers=8,
                refill_queue_capacity=32,
                continuity_policy=ContinuityPolicy.ALLOW_SEGMENTS,
                synchronization_mode="best_effort",
                peer_failure_policy=PeerFailurePolicy.FAIL_SESSION,
                storage_policy=DEVICE_AXIS_STORAGE_POLICY_V1,
                tags=("CAPTURE_ONLY", "DEVICE_AXIS_ZERO_FILL", "LIVE", "MIXED_RATE"),
            )
        )

    dwell_class = {
        5_000_000: ProductionDwellClass.MIXED_2P5_5,
        10_000_000: ProductionDwellClass.MIXED_2P5_10,
        15_000_000: ProductionDwellClass.MIXED_2P5_15,
    }[high_rate_hz]
    return compile_mixed_rate_capture_plan_v3(
        dwell_class=dwell_class,
        radio_ids=("radio-a", "radio-b"),
        profile_revisions_by_radio={
            "radio-a": revision(2_500_000),
            "radio-b": revision(high_rate_hz),
        },
        starlink_channel=3,
        starlink_edge=StarlinkEdge.UPPER,
        source_type=SourceType.LIVE,
    )


def _production_plan():
    duration = Decimal("0.000004")
    revisions: dict[tuple[int, tuple[int, ...], bool], CaptureProfileRevisionV2] = {}
    for rate, receivers, mixed in (
        (2_500_000, (0, 1), False),
        (5_000_000, (0, 1), False),
        (2_500_000, (0, 1), True),
        (5_000_000, (0, 1), True),
        *(
            (rate, (receiver,), True)
            for rate in (10_000_000, 15_000_000, 20_000_000)
            for receiver in (0, 1)
        ),
    ):
        revisions[(rate, receivers, mixed)] = CaptureProfileRevisionV2.from_profile(
            CaptureProfileV2(
                name=f"production-{rate}-rx{''.join(map(str, receivers))}-{int(mixed)}-test",
                center_frequency_hz=1_700_000_000,
                sample_rate_hz=rate,
                bandwidth_hz=rate,
                receivers=receivers,
                gain_mode=GainMode.MANUAL,
                gains=tuple(
                    ReceiverGainV1(receiver_id=receiver, gain_db=30.0) for receiver in receivers
                ),
                duration_seconds=duration,
                refill_samples=4,
                settle_seconds=Decimal(0),
                prime_refills=0,
                kernel_buffers=8,
                refill_queue_capacity=32,
                continuity_policy=ContinuityPolicy.ALLOW_SEGMENTS,
                synchronization_mode="best_effort",
                peer_failure_policy=PeerFailurePolicy.FAIL_SESSION,
                storage_policy=DEVICE_AXIS_STORAGE_POLICY_V1,
                tags=("CAPTURE_ONLY", "DEVICE_AXIS_ZERO_FILL", "LIVE", "PRODUCTION_RATE"),
            )
        )
    authority = {
        key: (revision.profile.name, revision.revision_digest, revision.profile.refill_samples)
        for key, revision in revisions.items()
    }
    intent = next(
        compile_production_dwell_intent_v2(
            operation_key=f"production-test:{ordinal}",
            cadence_ordinal=ordinal,
            radio_ids=("radio-a", "radio-b"),
            profile_authority=authority,
        )
        for ordinal in range(8)
        if compile_production_dwell_intent_v2(
            operation_key=f"production-test:{ordinal}",
            cadence_ordinal=ordinal,
            radio_ids=("radio-a", "radio-b"),
            profile_authority=authority,
        ).dwell_class
        is ProductionDwellClassV2.MIXED_2P5_20
    )
    selected = {
        leg.radio_id: revisions[(leg.sample_rate_hz, leg.receiver_ids, True)]
        for leg in intent.radio_legs
    }
    return compile_production_capture_plan_v4(
        intent=intent,
        profile_revisions_by_radio=selected,
        source_type=SourceType.LIVE,
    )


def _record_opened_bundles(
    coordinator: AcquisitionCoordinator,
    monkeypatch: pytest.MonkeyPatch,
) -> list[RecordingBundleWriter]:
    opened: list[RecordingBundleWriter] = []
    original_begin = coordinator.store.begin

    def begin(
        session_id: str,
        compression: CompressionSettingsV1,
        *,
        failure_injector: Callable[[str], None] | None = None,
    ) -> RecordingBundleWriter:
        writer = original_begin(
            session_id,
            compression,
            failure_injector=failure_injector,
        )
        opened.append(writer)
        return writer

    monkeypatch.setattr(coordinator.store, "begin", begin)
    return opened


def _assert_quarantined_v3_evidence(
    coordinator: AcquisitionCoordinator,
    session_id: str,
) -> Path:
    spool = coordinator.store.spool_root / f"{session_id}.partial"
    assert spool.is_dir()
    assert not (spool / "manifest.json").exists()
    assert not (spool / "manifest.json.partial").exists()
    assert any(path.is_file() for path in spool.rglob("*"))
    assert not list(coordinator.store.recordings_root.rglob(session_id))
    report = coordinator.store.reconcile()
    assert report.committed == ()
    assert report.issues == ()
    return spool


def test_v2_capture_resets_buffer_attests_k_and_persists_validated_chain(
    tmp_path: Path,
) -> None:
    radio = FakeRadioSource("radio-a")
    coordinator = _coordinator(tmp_path)

    result = coordinator.capture_once(
        _plan(sample_count=10),
        {"radio-a": radio},
        session_id="continuity-v2-complete",
    )

    assert result.state is CaptureState.COMMITTED
    assert isinstance(result.manifest, RecordingManifestV2)
    stream = result.manifest.streams[0]
    assert stream.state is StreamState.COMPLETE
    assert stream.continuity.sample_loss_observable is True
    assert stream.continuity.observed_sample_count == 10
    assert stream.continuity.device_span_sample_count == 10
    assert stream.continuity.kernel_buffers == 8
    assert stream.continuity.queue_capacity_refills == 32
    assert stream.continuity.queue_high_water_refills >= 1
    assert stream.timing is not None
    assert stream.timing.first_sample.estimate_utc_ns == 1_700_000_000_000_000_000
    assert stream.timing.first_sample.earliest_utc_ns == 1_699_999_999_999_999_989
    assert stream.timing.last_sample.estimate_utc_ns == 1_700_000_000_000_003_600
    assert stream.timing.last_sample.latest_utc_ns == 1_700_000_000_000_003_611
    assert stream.timing.first_sample.method is TimingMethod.DEVICE_COUNTER_ANCHORED
    assert radio.lifecycle[:4] == [
        "open",
        "reset_receive_buffer",
        "configure",
        "reset_receive_buffer",
    ]
    assert radio.lifecycle[4] == "begin_metadata_capture:4:8"
    assert radio.lifecycle[-1] == "close"
    inspected = coordinator.store.inspect("continuity-v2-complete")
    assert isinstance(inspected.manifest, RecordingManifestV2)
    reader = coordinator.store.reader(inspected, "stream-0")
    gap_map = reader.gap_map()
    assert gap_map.observed_sample_count == 10
    assert gap_map.device_span_sample_count == 10
    assert gap_map.boundaries == ()
    assert coordinator.store.verify(inspected).gap_map_count == 1
    blocks = list(reader.iter_blocks(block_samples=4))
    assert [block.metadata.device_sample_counter for block in blocks] == [0, 4, 8]
    assert [block.metadata.sample_count for block in blocks] == [4, 4, 2]
    assert all(block.metadata.schema_version == 2 for block in blocks)


@pytest.mark.parametrize("sample_rate_hz", (3_000_000, 5_000_000))
def test_v2_rate_mode_applies_one_exact_rate_to_both_radios(
    tmp_path: Path,
    sample_rate_hz: int,
) -> None:
    plan = _plan(
        radio_ids=("radio-a", "radio-b"),
        sample_count=10,
        sample_rate_hz=sample_rate_hz,
    )

    result = _coordinator(tmp_path).capture_once(
        plan,
        {
            "radio-a": FakeRadioSource("radio-a"),
            "radio-b": FakeRadioSource("radio-b"),
        },
        session_id=f"continuity-v2-{sample_rate_hz}",
    )

    assert result.state is CaptureState.COMMITTED
    assert isinstance(result.manifest, RecordingManifestV2)
    assert len(result.manifest.streams) == 2
    assert all(stream.state is StreamState.COMPLETE for stream in result.manifest.streams)
    assert {stream.requested_settings.sample_rate_hz for stream in result.manifest.streams} == {
        sample_rate_hz
    }
    assert {
        stream.applied_settings.sample_rate_hz
        for stream in result.manifest.streams
        if stream.applied_settings is not None
    } == {sample_rate_hz}
    assert all(
        isinstance(stream.continuity, ContinuitySummaryV2)
        and stream.continuity.observed_sample_count == 10
        and stream.continuity.device_span_sample_count == 10
        and stream.continuity.total_observed_gap_count == 0
        and stream.continuity.total_observed_overflow_count == 0
        for stream in result.manifest.streams
    )


def test_v2_fast_radio_drains_while_peer_is_still_arming(tmp_path: Path) -> None:
    slow_arm_entered = Event()
    fast_read_started = Event()
    lifecycle: list[str] = []
    lifecycle_lock = threading.Lock()

    def record(event: str) -> None:
        with lifecycle_lock:
            lifecycle.append(event)

    class FastRadio(FakeRadioSource):
        def begin_metadata_capture(self, *args, **kwargs) -> int:
            assert slow_arm_entered.wait(timeout=1.0)
            return super().begin_metadata_capture(*args, **kwargs)

        def read_block(self, sample_count: int) -> IqBlock:
            record("fast-read")
            fast_read_started.set()
            return super().read_block(sample_count)

    class SlowArmRadio(FakeRadioSource):
        def begin_metadata_capture(self, *args, **kwargs) -> int:
            record("slow-arm-entered")
            slow_arm_entered.set()
            assert fast_read_started.wait(timeout=1.0)
            result = super().begin_metadata_capture(*args, **kwargs)
            record("slow-arm-completed")
            return result

    result = _coordinator(tmp_path).capture_once(
        _plan(radio_ids=("radio-a", "radio-b"), sample_count=12),
        {
            "radio-a": FastRadio("radio-a"),
            "radio-b": SlowArmRadio("radio-b"),
        },
        session_id="continuity-v2-independent-arm-and-drain",
    )

    assert result.state is CaptureState.COMMITTED
    assert lifecycle.index("slow-arm-entered") < lifecycle.index("fast-read")
    assert lifecycle.index("fast-read") < lifecycle.index("slow-arm-completed")


@pytest.mark.parametrize("sample_rate_hz", (2_500_000, 3_000_000, 5_000_000, 10_000_000))
def test_device_axis_v3_lossless_capture_has_one_fixed_logical_iq_length(
    tmp_path: Path,
    sample_rate_hz: int,
) -> None:
    coordinator = _device_axis_coordinator(tmp_path)
    result = coordinator.capture_once(
        _device_axis_plan(sample_count=12, sample_rate_hz=sample_rate_hz),
        {"radio-a": FakeRadioSource("radio-a")},
        session_id=f"device-axis-lossless-{sample_rate_hz}",
    )

    assert result.state is CaptureState.COMMITTED
    assert isinstance(result.manifest, RecordingManifestV3)
    stream = result.manifest.streams[0]
    assert stream.state is StreamState.COMPLETE
    assert stream.logical_sample_count == stream.observed_sample_count == 12
    assert stream.zero_fill_sample_count == 0
    assert sum(chunk.uncompressed_bytes for chunk in stream.chunks) == 12 * 2 * 4
    assert stream.observed_iq_sha256 == stream.logical_iq_sha256
    assert stream.applied_settings.sample_rate_hz == sample_rate_hz
    inspected = coordinator.store.inspect(result.session_id)
    assert coordinator.store.verify(inspected).validity_inventory_count == 1
    span = coordinator.store.reader(inspected, "stream-0").read_device_span(0, 12)
    assert span.valid_samples.all()
    assert set(span.continuity_segment_ids) == {0}


def test_native_bandwidth_v3_rejects_even_one_hz_of_bandwidth_readback_drift(
    tmp_path: Path,
) -> None:
    class ShiftedReadbackRadio(FakeRadioSource):
        def configure(self, settings: RadioSettingsV1) -> RadioSettingsV1:
            super().configure(settings)
            return settings.model_copy(update={"bandwidth_hz": settings.bandwidth_hz - 1})

    coordinator = _device_axis_coordinator(tmp_path)
    result = coordinator.capture_once(
        _device_axis_plan(
            sample_count=12,
            sample_rate_hz=10_000_000,
            native_bandwidth=True,
        ),
        {"radio-a": ShiftedReadbackRadio("radio-a")},
        session_id="native-bandwidth-rf-readback-drift",
    )

    assert result.state is CaptureState.FAILED
    assert result.bundle is None
    assert any("bandwidth_hz readback mismatch" in error for error in result.errors)
    assert not coordinator.store.reconcile().committed


def test_device_axis_v3_internal_gap_is_physically_zero_filled_and_masked(
    tmp_path: Path,
) -> None:
    coordinator = _device_axis_coordinator(tmp_path)
    result = coordinator.capture_once(
        _device_axis_plan(sample_count=12),
        {"radio-a": FakeRadioSource("radio-a", gaps_before_blocks={1: 4})},
        session_id="device-axis-internal-gap",
    )

    assert result.state is CaptureState.DEGRADED
    assert isinstance(result.manifest, RecordingManifestV3)
    stream = result.manifest.streams[0]
    assert stream.state is StreamState.PARTIAL
    assert stream.logical_sample_count == 12
    assert stream.observed_sample_count == 8
    assert stream.zero_fill_sample_count == 4
    assert stream.continuity.device_span_sample_count == 12
    assert stream.continuity.missing_sample_count == 4
    assert sum(chunk.uncompressed_bytes for chunk in stream.chunks) == 12 * 2 * 4
    inspected = coordinator.store.inspect(result.session_id)
    dense = coordinator.store.read_ci16(inspected, "stream-0", 0, 12)
    assert not dense[4:8].any()
    span = coordinator.store.reader(inspected, "stream-0").read_device_span(0, 12)
    assert span.valid_samples.tolist() == [True] * 4 + [False] * 4 + [True] * 4
    assert span.continuity_segment_ids.tolist() == [0] * 4 + [-1] * 4 + [1] * 4


def test_device_axis_v3_terminal_gap_closes_iq_and_timing_at_requested_endpoint(
    tmp_path: Path,
) -> None:
    coordinator = _device_axis_coordinator(tmp_path)
    result = coordinator.capture_once(
        _device_axis_plan(sample_count=6),
        {"radio-a": FakeRadioSource("radio-a", gaps_before_blocks={1: 4})},
        session_id="device-axis-terminal-gap",
    )

    assert result.state is CaptureState.DEGRADED
    assert isinstance(result.manifest, RecordingManifestV3)
    stream = result.manifest.streams[0]
    assert stream.logical_sample_count == 6
    assert stream.observed_sample_count == 4
    assert stream.zero_fill_sample_count == 2
    terminal = stream.continuity.terminal_gap
    assert terminal is not None
    assert terminal.in_span_missing_sample_count == 2
    assert stream.timing.last_sample.estimate_utc_ns == (
        stream.timing.first_sample.estimate_utc_ns + 5 * 1_000_000_000 // 2_500_000
    )
    inspected = coordinator.store.inspect(result.session_id)
    reader = coordinator.store.reader(inspected, "stream-0")
    gap_map = reader.gap_map()
    validity = reader.validity_inventory()
    assert stream.continuity.segment_count == 1
    assert gap_map.segment_count == 2
    assert len(validity.segments) == 2
    terminal_segment = validity.segments[1]
    assert terminal_segment.device_sample_start == terminal_segment.device_sample_stop == 6
    assert terminal_segment.stored_sample_start == terminal_segment.stored_sample_stop == 4
    assert terminal_segment.preceding_boundary_reason == "terminal_counter_gap"
    span = reader.read_device_span(0, 6)
    assert span.valid_samples.tolist() == [True] * 4 + [False] * 2
    assert not span.samples[4:].any()


def test_device_axis_v3_fail_session_never_publishes_an_unclosed_peer(
    tmp_path: Path,
) -> None:
    clean_reads_complete = Event()

    class CleanRadio(FakeRadioSource):
        def __init__(self) -> None:
            super().__init__("radio-a")
            self._test_reads = 0

        def read_block(self, sample_count: int) -> IqBlock:
            block = super().read_block(sample_count)
            self._test_reads += 1
            if self._test_reads == 3:
                clean_reads_complete.set()
            return block

    class FailureAfterCleanEndpoint(FakeRadioSource):
        def __init__(self) -> None:
            super().__init__("radio-b")
            self._test_reads = 0

        def read_block(self, sample_count: int) -> IqBlock:
            if self._test_reads == 1:
                assert clean_reads_complete.wait(timeout=1.0)
                raise RuntimeError("injected peer failure after clean endpoint")
            block = super().read_block(sample_count)
            self._test_reads += 1
            return block

    coordinator = _device_axis_coordinator(tmp_path)
    result = coordinator.capture_once(
        _device_axis_plan(radio_ids=("radio-a", "radio-b"), sample_count=12),
        {
            "radio-a": CleanRadio(),
            "radio-b": FailureAfterCleanEndpoint(),
        },
        session_id="device-axis-failed-peer",
    )

    assert result.state is CaptureState.FAILED
    assert result.manifest is None
    assert any("peer-failure policy rejected" in error for error in result.errors)
    with pytest.raises(Exception, match="does not exist"):
        coordinator.store.inspect(result.session_id)
    spool = _assert_quarantined_v3_evidence(coordinator, result.session_id)
    assert (spool / "radio-radio-a" / "validity-inventory.json").is_file()
    assert (spool / "radio-radio-b").is_dir()


def test_device_axis_v3_unknown_endpoint_is_quarantined_without_a_manifest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    coordinator = _device_axis_coordinator(tmp_path)
    opened = _record_opened_bundles(coordinator, monkeypatch)

    result = coordinator.capture_once(
        _device_axis_plan(sample_count=12),
        {"radio-a": FakeRadioSource("radio-a", fail_after_blocks=1)},
        session_id="device-axis-unknown-endpoint",
    )

    assert result.state is CaptureState.FAILED
    assert result.manifest is None
    assert result.bundle is None
    assert any("endpoint is unproven" in error for error in result.errors)
    assert len(opened) == 1 and opened[0].quarantined
    _assert_quarantined_v3_evidence(coordinator, result.session_id)


def test_device_axis_v3_inflight_cancellation_quarantines_observed_prefix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cancel = Event()

    class CancelAfterFirstRefill(FakeRadioSource):
        def __init__(self) -> None:
            super().__init__("radio-a")
            self._test_reads = 0

        def read_block(self, sample_count: int) -> IqBlock:
            block = super().read_block(sample_count)
            self._test_reads += 1
            if self._test_reads == 1:
                cancel.set()
            return block

    coordinator = _device_axis_coordinator(tmp_path)
    opened = _record_opened_bundles(coordinator, monkeypatch)
    result = coordinator.capture_once(
        _device_axis_plan(sample_count=12),
        {"radio-a": CancelAfterFirstRefill()},
        session_id="device-axis-inflight-cancel",
        cancel=cancel,
    )

    assert result.state is CaptureState.FAILED
    assert result.manifest is None
    assert result.bundle is None
    assert any("capture cancelled; no manifest was published" in error for error in result.errors)
    assert len(opened) == 1 and opened[0].quarantined
    _assert_quarantined_v3_evidence(coordinator, result.session_id)


def test_device_axis_v3_writer_failure_quarantines_observed_prefix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = DeviceAxisStreamBundleWriter.append

    def fail_after_observed_write(
        self: DeviceAxisStreamBundleWriter,
        block: IqBlock,
    ) -> None:
        original(self, block)
        raise OSError("injected V3 writer failure")

    monkeypatch.setattr(DeviceAxisStreamBundleWriter, "append", fail_after_observed_write)
    coordinator = _device_axis_coordinator(tmp_path)
    opened = _record_opened_bundles(coordinator, monkeypatch)
    result = coordinator.capture_once(
        _device_axis_plan(sample_count=12),
        {"radio-a": FakeRadioSource("radio-a")},
        session_id="device-axis-writer-failure",
    )

    assert result.state is CaptureState.FAILED
    assert result.manifest is None
    assert result.bundle is None
    assert any("injected V3 writer failure" in error for error in result.errors)
    assert len(opened) == 1 and opened[0].quarantined
    _assert_quarantined_v3_evidence(coordinator, result.session_id)


def test_device_axis_v3_queue_failure_refuses_a_fixed_length_manifest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = DeviceAxisStreamBundleWriter.append
    first = True

    def delayed_append(self, block):
        nonlocal first
        if first:
            first = False
            time.sleep(0.1)
        return original(self, block)

    monkeypatch.setattr(DeviceAxisStreamBundleWriter, "append", delayed_append)
    coordinator = _device_axis_coordinator(tmp_path)
    result = coordinator.capture_once(
        _device_axis_plan(sample_count=12, queue_capacity=1),
        {"radio-a": FakeRadioSource("radio-a")},
        session_id="device-axis-queue-refusal",
    )

    assert result.state is CaptureState.FAILED
    assert result.manifest is None
    assert any("queue full" in error or "enqueue failure" in error for error in result.errors)
    with pytest.raises(Exception, match="does not exist"):
        coordinator.store.inspect(result.session_id)
    _assert_quarantined_v3_evidence(coordinator, result.session_id)


def test_legacy_live_plan_fails_closed_before_radio_prepare(tmp_path: Path) -> None:
    v2_profile = _plan(sample_count=4).profile_revision.profile
    legacy_document = v2_profile.model_dump(
        mode="json",
        exclude={
            "schema_version",
            "kernel_buffers",
            "refill_queue_capacity",
            "require_device_metadata",
        },
    )
    legacy_document["schema_version"] = 1
    legacy = compile_capture_plan(
        CaptureProfileRevisionV1.from_profile(CaptureProfileV1.model_validate(legacy_document)),
        ("radio-a",),
        source_type=SourceType.LIVE,
    )
    radio = FakeRadioSource("radio-a")

    result = _coordinator(tmp_path).capture_once(
        legacy,
        {"radio-a": radio},
        session_id="legacy-live-rejected",
    )

    assert result.state is CaptureState.FAILED
    assert result.manifest is None
    assert radio.lifecycle == []
    assert any("CapturePlanV2" in error for error in result.errors)


def test_positive_gap_covers_requested_device_span_and_seals_degraded_evidence(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    coordinator = _coordinator(tmp_path)
    caplog.set_level(logging.ERROR, logger="leo.acquisition.coordinator")

    result = coordinator.capture_once(
        _plan(sample_count=12),
        {"radio-a": FakeRadioSource("radio-a", gaps_before_blocks={1: 4})},
        session_id="continuity-v2-gap",
    )

    assert result.state is CaptureState.DEGRADED
    assert isinstance(result.manifest, RecordingManifestV2)
    stream = result.manifest.streams[0]
    assert stream.state is StreamState.PARTIAL
    assert stream.captured_sample_count == 8
    assert stream.continuity.observed_sample_count == 8
    assert stream.continuity.device_span_sample_count == 12
    assert stream.continuity.gap_count == 1
    assert stream.continuity.missing_sample_count == 4
    assert stream.error is not None and "missing_samples=4" in stream.error
    assert [chunk.segment_index for chunk in stream.chunks] == [0, 1]
    assert any(
        record.getMessage() == "radio=radio-a stream=fake-generation-1 expected_counter=4 "
        "actual_counter=8 missing_samples=4 missing_seconds=0.000001600"
        for record in caplog.records
    )
    inspected = coordinator.store.inspect("continuity-v2-gap")
    reader = coordinator.store.reader(inspected, "stream-0")
    gap_map = reader.gap_map()
    assert gap_map.missing_sample_count == 4
    device_blocks = tuple(iter_masked_device_iq(reader, gap_map, block_samples=4))
    assert sum(block.sample_count for block in device_blocks) == 12
    assert sum(block.sample_count - int(block.valid_samples.sum()) for block in device_blocks) == 4
    dense = reader.read_device_span(2, 8)
    assert dense.valid_samples.tolist() == [True, True, False, False, False, False, True, True]
    assert dense.continuity_segment_ids.tolist() == [0, 0, -1, -1, -1, -1, 1, 1]
    assert not dense.samples[2:6].any()
    assert (
        sum(block.metadata.sample_count for block in reader.iter_observed_spans(block_samples=4))
        == 8
    )


def test_first_refill_overflow_seals_degraded_gap_map_without_inventing_loss(
    tmp_path: Path,
) -> None:
    coordinator = _coordinator(tmp_path)
    result = coordinator.capture_once(
        _plan(sample_count=8),
        {"radio-a": FakeRadioSource("radio-a", overflow_blocks={0})},
        session_id="continuity-v2-first-overflow",
    )

    assert result.state is CaptureState.DEGRADED
    assert isinstance(result.manifest, RecordingManifestV2)
    stream = result.manifest.streams[0]
    assert stream.continuity.overflow_count == 1
    assert stream.continuity.missing_sample_count == 0
    reader = coordinator.store.reader(
        coordinator.store.inspect("continuity-v2-first-overflow"),
        "stream-0",
    )
    gap_map = reader.gap_map()
    assert gap_map.capture_start_overflow is True
    assert gap_map.capture_start_header_evidence_sha256 is not None
    assert gap_map.boundaries == ()


def test_require_contiguous_stops_after_persisting_offending_refill(tmp_path: Path) -> None:
    coordinator = _coordinator(tmp_path)

    result = coordinator.capture_once(
        _plan(
            sample_count=20,
            continuity_policy=ContinuityPolicy.REQUIRE_CONTIGUOUS,
        ),
        {"radio-a": FakeRadioSource("radio-a", gaps_before_blocks={1: 4})},
        session_id="continuity-v2-require-stops",
    )

    assert result.state is CaptureState.DEGRADED
    assert isinstance(result.manifest, RecordingManifestV2)
    stream = result.manifest.streams[0]
    assert stream.captured_sample_count == 8
    assert stream.continuity.device_span_sample_count == 12
    assert stream.continuity.missing_sample_count == 4
    assert stream.error is not None and "continuity policy" in stream.error


def test_gap_that_crosses_capture_end_persists_terminal_header_without_iq_overrun(
    tmp_path: Path,
) -> None:
    coordinator = _coordinator(tmp_path)

    result = coordinator.capture_once(
        _plan(sample_count=6),
        {"radio-a": FakeRadioSource("radio-a", gaps_before_blocks={1: 4})},
        session_id="continuity-v2-terminal-gap",
    )

    assert result.state is CaptureState.DEGRADED
    assert isinstance(result.manifest, RecordingManifestV2)
    stream = result.manifest.streams[0]
    assert stream.captured_sample_count == 4
    assert stream.continuity.observed_sample_count == 4
    assert stream.continuity.device_span_sample_count == 6
    assert stream.continuity.missing_sample_count == 2
    terminal = stream.continuity.terminal_gap
    assert terminal is not None
    assert terminal.expected_device_sample_counter == 4
    assert terminal.actual_device_sample_counter == 8
    assert terminal.actual_missing_sample_count == 4
    assert terminal.in_span_missing_sample_count == 2
    assert sum(chunk.sample_count for chunk in stream.chunks) == 4
    inspected = coordinator.store.inspect("continuity-v2-terminal-gap")
    reader = coordinator.store.reader(inspected, "stream-0")
    gap_map = reader.gap_map()
    assert gap_map.device_span_sample_count == 6
    assert stream.continuity.segment_count == 1
    assert gap_map.segment_count == 2
    assert len(gap_map.boundaries) == stream.continuity.gap_count == 1
    assert gap_map.missing_sample_count == stream.continuity.missing_sample_count
    assert gap_map.boundaries[0].observed_counter_gap_sample_count == 4
    assert gap_map.boundaries[0].missing_sample_count == 2
    device_blocks = tuple(iter_masked_device_iq(reader, gap_map, block_samples=4))
    assert [block.sample_count for block in device_blocks] == [4, 2]
    assert [block.is_zero_fill for block in device_blocks] == [False, True]
    dense = reader.read_device_span(0, 6)
    assert dense.valid_samples.tolist() == [True, True, True, True, False, False]
    assert dense.continuity_segment_ids.tolist() == [0, 0, 0, 0, -1, -1]


def test_injected_slow_writer_never_blocks_refill_and_queue_full_is_persisted(
    tmp_path: Path,
    monkeypatch,
) -> None:
    original = StreamBundleWriter.append
    calls = 0

    def delayed_append(self, block):
        nonlocal calls
        calls += 1
        if calls == 1:
            time.sleep(0.1)
        return original(self, block)

    monkeypatch.setattr(StreamBundleWriter, "append", delayed_append)
    coordinator = _coordinator(tmp_path)

    result = coordinator.capture_once(
        _plan(sample_count=12, queue_capacity=1),
        {"radio-a": FakeRadioSource("radio-a")},
        session_id="continuity-v2-queue-full",
    )

    assert result.state is CaptureState.DEGRADED
    assert isinstance(result.manifest, RecordingManifestV2)
    stream = result.manifest.streams[0]
    assert isinstance(stream.continuity, ContinuitySummaryV2)
    assert stream.state is StreamState.PARTIAL
    assert stream.continuity.enqueue_failure_count == 1
    assert stream.continuity.queue_capacity_refills == 1
    assert stream.continuity.queue_high_water_refills == 1
    terminal = stream.continuity.terminal_enqueue_failure
    assert terminal is not None
    assert stream.continuity.last_device_sample_counter is not None
    assert stream.continuity.last_source_sequence is not None
    assert terminal.device_sample_counter == stream.continuity.last_device_sample_counter + 1
    assert terminal.source_sequence == stream.continuity.last_source_sequence + 1
    assert terminal.session_sample_start == stream.captured_sample_count
    assert terminal.sample_count == 4
    assert stream.error is not None and "queue full" in stream.error


def test_queue_capacity_cannot_be_reused_before_dequeue_accounting(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """A dequeued-but-unaccounted item must still consume its bounded slot."""

    import leo.acquisition.coordinator as coordinator_module

    consumer_dequeued = Event()
    release_consumer = Event()

    class PausedAfterGetQueue(queue.Queue[object]):
        def get(self, block=True, timeout=None):
            item = super().get(block=block, timeout=timeout)
            if not consumer_dequeued.is_set():
                consumer_dequeued.set()
                assert release_consumer.wait(timeout=1.0)
            return item

    class RaceWindowRadio(FakeRadioSource):
        def __init__(self) -> None:
            super().__init__("radio-a")
            self._reads = 0

        def read_block(self, sample_count: int) -> IqBlock:
            if self._reads == 1:
                assert consumer_dequeued.wait(timeout=1.0)
                threading.Timer(0.05, release_consumer.set).start()
            block = super().read_block(sample_count)
            self._reads += 1
            return block

    monkeypatch.setattr(coordinator_module.queue, "Queue", PausedAfterGetQueue)
    result = _coordinator(tmp_path).capture_once(
        _plan(sample_count=12, queue_capacity=1),
        {"radio-a": RaceWindowRadio()},
        session_id="continuity-v2-dequeue-accounting-race",
    )

    assert result.state is CaptureState.DEGRADED
    assert isinstance(result.manifest, RecordingManifestV2)
    continuity = result.manifest.streams[0].continuity
    assert isinstance(continuity, ContinuitySummaryV2)
    assert continuity.queue_capacity_refills == 1
    assert continuity.queue_high_water_refills == 1
    assert continuity.enqueue_failure_count == 1


def _capture_with_terminal_rejected_header(
    tmp_path: Path,
    monkeypatch,
    *,
    gaps_before_blocks: dict[int, int] | None = None,
    overflow_blocks: set[int] | None = None,
):
    consumer_entered = Event()
    original_append = StreamBundleWriter.append
    append_calls = 0

    def delayed_first_append(self, block):
        nonlocal append_calls
        append_calls += 1
        if append_calls == 1:
            consumer_entered.set()
            time.sleep(0.1)
        return original_append(self, block)

    class ConsumerFencedRadio(FakeRadioSource):
        def __init__(self) -> None:
            super().__init__(
                "radio-a",
                gaps_before_blocks=gaps_before_blocks,
                overflow_blocks=overflow_blocks or (),
            )
            self._audit_reads = 0

        def read_block(self, sample_count: int) -> IqBlock:
            if self._audit_reads == 1:
                assert consumer_entered.wait(timeout=1.0)
            block = super().read_block(sample_count)
            self._audit_reads += 1
            return block

    monkeypatch.setattr(StreamBundleWriter, "append", delayed_first_append)
    result = _coordinator(tmp_path).capture_once(
        _plan(sample_count=16, queue_capacity=1),
        {"radio-a": ConsumerFencedRadio()},
        session_id="terminal-rejected-evidence",
    )
    assert isinstance(result.manifest, RecordingManifestV2)
    return result


def test_queue_full_gap_header_is_counted_outside_the_reconstructable_span(
    tmp_path: Path,
    monkeypatch,
) -> None:
    result = _capture_with_terminal_rejected_header(
        tmp_path,
        monkeypatch,
        gaps_before_blocks={2: 4},
    )

    stream = result.manifest.streams[0]
    continuity = stream.continuity
    assert result.state is CaptureState.DEGRADED
    assert continuity.gap_count == 0
    assert continuity.missing_sample_count == 0
    assert continuity.terminal_rejected_gap_count == 1
    assert continuity.terminal_rejected_missing_sample_count == 4
    assert continuity.terminal_rejected_overflow_count == 0
    assert continuity.total_observed_gap_count == 1
    assert continuity.total_observed_missing_sample_count == 4
    terminal = continuity.terminal_enqueue_failure
    assert terminal is not None
    assert terminal.continuity.value == "gap_before"
    assert terminal.missing_samples_before == 4

    store = RecordingStore(tmp_path / "bulk")
    gap_map = store.reader(store.inspect("terminal-rejected-evidence"), "stream-0").gap_map()
    assert gap_map.boundaries == ()
    assert gap_map.device_span_sample_count == continuity.device_span_sample_count == 8
    rejected = gap_map.terminal_rejected_refill
    assert rejected is not None
    assert rejected.reason == "queue_full_counter_gap"
    assert rejected.stored_sample_offset == 8
    assert rejected.device_sample_offset == 8
    assert rejected.observed_counter_gap_sample_count == 4


def test_queue_full_overflow_header_is_counted_outside_the_reconstructable_span(
    tmp_path: Path,
    monkeypatch,
) -> None:
    result = _capture_with_terminal_rejected_header(
        tmp_path,
        monkeypatch,
        overflow_blocks={2},
    )

    continuity = result.manifest.streams[0].continuity
    assert result.state is CaptureState.DEGRADED
    assert continuity.overflow_count == 0
    assert continuity.terminal_rejected_gap_count == 0
    assert continuity.terminal_rejected_missing_sample_count == 0
    assert continuity.terminal_rejected_overflow_count == 1
    assert continuity.total_observed_overflow_count == 1
    terminal = continuity.terminal_enqueue_failure
    assert terminal is not None
    assert terminal.continuity.value == "overflow"
    assert terminal.overflow_observed is True

    store = RecordingStore(tmp_path / "bulk")
    gap_map = store.reader(store.inspect("terminal-rejected-evidence"), "stream-0").gap_map()
    rejected = gap_map.terminal_rejected_refill
    assert rejected is not None
    assert rejected.reason == "queue_full_overflow"
    assert rejected.observed_counter_gap_sample_count == 0
    assert rejected.overflow_observed is True


def test_consumer_crash_with_full_queue_has_bounded_shutdown(
    tmp_path: Path,
    monkeypatch,
) -> None:
    def crash_after_queue_fills(self, block):
        time.sleep(0.05)
        raise KeyboardInterrupt("injected consumer crash")

    monkeypatch.setattr(StreamBundleWriter, "append", crash_after_queue_fills)
    coordinator = _coordinator(tmp_path)
    started = time.monotonic()

    result = coordinator.capture_once(
        _plan(sample_count=20, queue_capacity=1),
        {"radio-a": FakeRadioSource("radio-a")},
        session_id="continuity-v2-consumer-crash",
    )

    assert time.monotonic() - started < 2.0
    assert result.state is CaptureState.FAILED
    assert result.manifest is None
    assert any("consumer" in error.lower() for error in result.errors)


def test_timed_out_consumer_quarantines_spool_and_cannot_publish_late(
    tmp_path: Path,
    monkeypatch,
) -> None:
    entered_finalize = Event()
    release_finalize = Event()
    original = StreamBundleWriter.finalize

    def blocked_finalize(self, **kwargs):
        entered_finalize.set()
        assert release_finalize.wait(timeout=2.0)
        return original(self, **kwargs)

    monkeypatch.setattr(StreamBundleWriter, "finalize", blocked_finalize)
    store_root = tmp_path / "bulk"
    coordinator = AcquisitionCoordinator(
        RecordingStore(store_root),
        compression=CompressionSettingsV1(
            policy_id="test-zstd-v1",
            target_uncompressed_bytes=1024,
        ),
        config=AcquisitionConfig(
            safety_reserve_bytes=0,
            consumer_shutdown_timeout_seconds=0.02,
        ),
        free_bytes=lambda _path: 10**12,
    )

    result = coordinator.capture_once(
        _plan(sample_count=4, source_type=SourceType.TEST),
        {"radio-a": FakeRadioSource("radio-a")},
        session_id="continuity-v2-finalize-timeout",
    )

    assert entered_finalize.is_set()
    assert result.state is CaptureState.FAILED
    assert result.manifest is None
    spool = store_root / "spool" / "continuity-v2-finalize-timeout.partial"
    assert spool.is_dir()
    assert not (spool / "manifest.json").exists()
    assert not list((store_root / "recordings").rglob("continuity-v2-finalize-timeout"))

    release_finalize.set()
    deadline = time.monotonic() + 1.0
    while any(path.name.endswith(".partial") for path in spool.rglob("*")):
        assert time.monotonic() < deadline
        time.sleep(0.01)
    assert not (spool / "manifest.json").exists()
    assert not list((store_root / "recordings").rglob("continuity-v2-finalize-timeout"))


def test_first_stream_fsync_hang_cannot_block_quarantine_or_publish_late(
    tmp_path: Path,
    monkeypatch,
) -> None:
    session_id = "continuity-v2-open-stream-timeout"
    entered_fsync = Event()
    release_fsync = Event()
    completed_fsync = Event()
    original_fsync = storage_writer._fsync_directory

    def blocked_first_stream_fsync(path: Path) -> None:
        if path.name == f"{session_id}.partial":
            entered_fsync.set()
            assert release_fsync.wait(timeout=2.0)
            try:
                original_fsync(path)
            finally:
                completed_fsync.set()
            return
        original_fsync(path)

    monkeypatch.setattr(storage_writer, "_fsync_directory", blocked_first_stream_fsync)

    class CloseInterruptRadio(FakeRadioSource):
        def close(self) -> None:
            super().close()
            raise KeyboardInterrupt("injected source close interrupt")

    store_root = tmp_path / "bulk"
    coordinator = AcquisitionCoordinator(
        RecordingStore(store_root),
        compression=CompressionSettingsV1(
            policy_id="test-zstd-v1",
            target_uncompressed_bytes=1024,
        ),
        config=AcquisitionConfig(
            safety_reserve_bytes=0,
            consumer_shutdown_timeout_seconds=0.02,
        ),
        free_bytes=lambda _path: 10**12,
    )
    resource = RadioResource(
        radio_id="radio-a",
        serial="serial-a",
        endpoint="fake:radio-a",
    )
    authority = LocalCaptureAuthority(tmp_path / "control", (resource,))
    application = AuthorizedAcquisitionApplication(
        AcquisitionApplication(coordinator),
        authority,
        CaptureTaskKind.SCHEDULED_RECORDING,
    )
    radio = CloseInterruptRadio("radio-a")
    started = time.monotonic()

    try:
        with pytest.raises(AcquisitionSupervisorPoisoned) as raised:
            application.once(
                _plan(sample_count=4),
                {"radio-a": radio},
                session_id=session_id,
            )

        assert entered_fsync.is_set()
        assert time.monotonic() - started < 1.0
        assert raised.value.session_id == session_id
        assert any("bounded timeout" in error for error in raised.value.errors)
        assert any("source close interrupt" in error for error in raised.value.errors)
        assert radio.lifecycle[-1] == "close"
        with pytest.raises(RadioBusyError, match="radio lease is busy"):
            authority.claim(
                ("radio-a",),
                task_id="next-dwell-must-not-start",
                task_kind=CaptureTaskKind.SCHEDULED_RECORDING,
            )
    finally:
        release_fsync.set()

    assert completed_fsync.wait(timeout=1.0)
    deadline = time.monotonic() + 1.0
    while any(thread.name == "leo-store-stream-0" for thread in threading.enumerate()):
        assert time.monotonic() < deadline
        time.sleep(0.01)
    while True:
        try:
            released = authority.claim(
                ("radio-a",),
                task_id="next-dwell-after-writer-stopped",
                task_kind=CaptureTaskKind.SCHEDULED_RECORDING,
            )
        except RadioBusyError:
            assert time.monotonic() < deadline
            time.sleep(0.01)
        else:
            released.release()
            break
    spool = store_root / "spool" / f"{session_id}.partial"
    assert spool.is_dir()
    assert not (spool / "manifest.json").exists()
    assert not list((store_root / "recordings").rglob(session_id))


def test_source_close_keyboard_interrupt_propagates_when_no_writer_is_poisoned(
    tmp_path: Path,
) -> None:
    class CloseInterruptRadio(FakeRadioSource):
        def close(self) -> None:
            super().close()
            raise KeyboardInterrupt("ordinary source close interrupt")

    radio = CloseInterruptRadio("radio-a")
    peer = FakeRadioSource("radio-b")

    with pytest.raises(KeyboardInterrupt, match="ordinary source close interrupt"):
        _coordinator(tmp_path).capture_once(
            _plan(radio_ids=("radio-a", "radio-b"), sample_count=4),
            {"radio-a": radio, "radio-b": peer},
            session_id="continuity-v2-close-interrupt",
        )

    assert radio.lifecycle[-1] == "close"
    assert peer.lifecycle[-1] == "close"


def test_read_block_keyboard_interrupt_cleans_bundle_and_releases_radio_lease(
    tmp_path: Path,
) -> None:
    class ReadInterruptRadio(FakeRadioSource):
        def read_block(self, sample_count: int) -> IqBlock:
            raise KeyboardInterrupt(f"injected read interrupt for {sample_count} samples")

    store_root = tmp_path / "bulk"
    coordinator = AcquisitionCoordinator(
        RecordingStore(store_root),
        compression=CompressionSettingsV1(
            policy_id="test-zstd-v1",
            target_uncompressed_bytes=1024,
        ),
        config=AcquisitionConfig(safety_reserve_bytes=0),
        free_bytes=lambda _path: 10**12,
    )
    resource = RadioResource("radio-a", "serial-a", "fake:radio-a")
    authority = LocalCaptureAuthority(tmp_path / "control", (resource,))
    application = AuthorizedAcquisitionApplication(
        AcquisitionApplication(coordinator),
        authority,
        CaptureTaskKind.SCHEDULED_RECORDING,
    )
    radio = ReadInterruptRadio("radio-a")
    started = time.monotonic()

    with pytest.raises(KeyboardInterrupt, match="injected read interrupt"):
        application.once(
            _plan(sample_count=4),
            {"radio-a": radio},
            session_id="continuity-v2-read-interrupt",
        )

    assert time.monotonic() - started < 1.0
    assert radio.lifecycle[-1] == "close"
    lease = authority.claim(
        ("radio-a",),
        task_id="next-dwell-after-read-interrupt",
        task_kind=CaptureTaskKind.SCHEDULED_RECORDING,
    )
    lease.release()
    spool = store_root / "spool" / "continuity-v2-read-interrupt.partial"
    assert spool.is_dir()
    assert not (spool / "manifest.json").exists()
    assert not list((store_root / "recordings").rglob("continuity-v2-read-interrupt"))


def test_readiness_base_exception_aborts_gate_and_closes_both_radios(
    tmp_path: Path,
    monkeypatch,
) -> None:
    def interrupt_readiness(_self, _timeout_seconds, _cancel) -> None:
        raise SystemExit("injected readiness interruption")

    monkeypatch.setattr(
        acquisition_coordinator._ReadinessGate,
        "wait_until_ready",
        interrupt_readiness,
    )
    radios = {
        "radio-a": FakeRadioSource("radio-a"),
        "radio-b": FakeRadioSource("radio-b"),
    }
    started = time.monotonic()

    with pytest.raises(SystemExit, match="injected readiness interruption"):
        _coordinator(tmp_path).capture_once(
            _plan(radio_ids=("radio-a", "radio-b"), sample_count=4),
            radios,
            session_id="continuity-v2-readiness-interrupt",
        )

    assert time.monotonic() - started < 1.0
    assert all(radio.lifecycle[-1] == "close" for radio in radios.values())
    spool = tmp_path / "bulk" / "spool" / "continuity-v2-readiness-interrupt.partial"
    assert spool.is_dir()
    assert not (spool / "manifest.json").exists()


def test_prepare_base_exception_closes_prepared_peer_before_propagating(
    tmp_path: Path,
) -> None:
    class PrepareInterruptRadio(FakeRadioSource):
        def configure(self, settings: RadioSettingsV1) -> RadioSettingsV1:
            raise KeyboardInterrupt("injected prepare interruption")

    interrupted = PrepareInterruptRadio("radio-a")
    peer = FakeRadioSource("radio-b")
    started = time.monotonic()

    with pytest.raises(KeyboardInterrupt, match="injected prepare interruption"):
        _coordinator(tmp_path).capture_once(
            _plan(radio_ids=("radio-a", "radio-b"), sample_count=4),
            {"radio-a": interrupted, "radio-b": peer},
            session_id="continuity-v2-prepare-interrupt",
        )

    assert time.monotonic() - started < 1.0
    assert interrupted.lifecycle[-1] == "close"
    assert peer.lifecycle[-1] == "close"
    assert not (tmp_path / "bulk" / "spool" / "continuity-v2-prepare-interrupt.partial").exists()


def test_storage_writer_independently_rejects_false_contiguous_declaration(
    tmp_path: Path,
) -> None:
    plan = _plan(source_type=SourceType.TEST)
    profile = plan.profile_revision.profile
    settings = RadioSettingsV1(
        center_frequency_hz=profile.center_frequency_hz,
        sample_rate_hz=profile.sample_rate_hz,
        bandwidth_hz=profile.bandwidth_hz,
        receiver_ids=profile.receivers,
        gain_mode=profile.gain_mode,
        gains=profile.gains,
    )
    radio = FakeRadioSource("radio-a")
    radio.open()
    radio.configure(settings)
    radio.begin_metadata_capture(4, kernel_buffers=8)
    first = radio.read_block(4)
    second = radio.read_block(4)
    false_metadata = second.metadata.model_copy(
        update={
            "device_sample_counter": 8,
            "source_sequence": 2,
            "continuity": "contiguous",
        }
    )
    false_block = IqBlock(samples=second.samples, metadata=false_metadata)
    store = RecordingStore(tmp_path / "independent-writer")
    bundle = store.begin(
        "writer-independent-validation",
        CompressionSettingsV1(policy_id="test-zstd-v1"),
    )
    stream = bundle.open_stream(
        "stream-0",
        radio.identity,
        (0, 1),
        counter_authoritative=True,
        kernel_buffers=8,
    )
    stream.append(first)

    with pytest.raises(RuntimeError, match="declared continuity"):
        stream.append(false_block)

    stream.abort()
    bundle.close()
    radio.close()


@pytest.mark.parametrize("high_rate_hz", (5_000_000, 10_000_000, 15_000_000))
def test_mixed_rate_capture_publishes_exact_per_radio_device_axes(
    tmp_path: Path,
    high_rate_hz: int,
) -> None:
    plan = _mixed_rate_plan(high_rate_hz)
    coordinator = _device_axis_coordinator(tmp_path)

    result = coordinator.capture_once(
        plan,
        {
            "radio-a": FakeRadioSource("radio-a", seed=1),
            "radio-b": FakeRadioSource("radio-b", seed=2),
        },
        session_id=f"mixed-{high_rate_hz}",
    )

    assert result.state is CaptureState.COMMITTED
    assert isinstance(result.manifest, RecordingManifestV4)
    assert tuple(stream.applied_settings.sample_rate_hz for stream in result.manifest.streams) == (
        2_500_000,
        high_rate_hz,
    )
    assert tuple(stream.logical_sample_count for stream in result.manifest.streams) == (
        10,
        high_rate_hz * 4 // 1_000_000,
    )
    assert result.manifest.synchronization.stream_ids == ("stream-0", "stream-1")
    assert coordinator.store.verify(f"mixed-{high_rate_hz}").validity_inventory_count == 2


def test_production_capture_persists_single_rx_tandem_evidence_and_v5_plan(
    tmp_path: Path,
) -> None:
    plan = _production_plan()
    coordinator = _device_axis_coordinator(tmp_path)

    result = coordinator.capture_once(
        plan,
        {
            "radio-a": FakeRadioSource("radio-a", seed=1),
            "radio-b": FakeRadioSource("radio-b", seed=2),
        },
        session_id="production-v5-single-rx",
    )

    assert result.state is CaptureState.COMMITTED
    assert type(result.manifest) is RecordingManifestV5
    assert result.manifest.capture_plan == plan
    high_stream = next(
        stream
        for stream in result.manifest.streams
        if stream.applied_settings.sample_rate_hz == 20_000_000
    )
    assert len(high_stream.applied_settings.receiver_ids) == 1
    assert high_stream.continuity.metadata_abi_version == 3
    assert high_stream.timeline_sha256 is not None
    assert coordinator.store.verify("production-v5-single-rx").validity_inventory_count == 2


def test_direct_async_capture_reopens_segments_and_persists_counter_loss(
    tmp_path: Path,
) -> None:
    frame_samples = 1_048_576
    coordinator = AcquisitionCoordinator(
        RecordingStore(tmp_path / "bulk"),
        compression=CompressionSettingsV1(
            policy_id=DEVICE_AXIS_STORAGE_POLICY_V1,
            target_uncompressed_bytes=128 * 1024 * 1024,
        ),
        config=AcquisitionConfig(safety_reserve_bytes=0),
        free_bytes=lambda _path: 10**12,
    )

    class ConstantFrameRadio(FakeRadioSource):
        def __init__(self, *args, **kwargs) -> None:
            super().__init__(*args, **kwargs)
            self._frame = np.zeros((frame_samples, 1, 2), dtype="<i2")

        def _samples(self, sample_count: int, receiver_ids: tuple[int, ...]) -> np.ndarray:
            assert sample_count == frame_samples
            assert receiver_ids == (0,)
            return self._frame

    radio = ConstantFrameRadio(
        "radio-a",
        gaps_before_blocks={1: 64 * frame_samples},
    )

    result = coordinator.capture_once(
        _direct_async_plan(),
        {"radio-a": radio},
        session_id="direct-async-two-segments",
    )

    assert result.state is CaptureState.DEGRADED
    assert isinstance(result.manifest, RecordingManifestV3)
    stream = result.manifest.streams[0]
    assert stream.state is StreamState.PARTIAL
    assert stream.continuity.gap_count == 1
    assert stream.continuity.missing_sample_count == (63 * frame_samples + 1)
    assert radio.lifecycle.count("begin_metadata_capture:1048576:15") == 2
    timeline = next(
        coordinator.store.reader(result.bundle, stream.stream_id).iter_timeline_metadata()
    )
    evidence = DirectAsyncEvidenceV1.model_validate(
        timeline.hardware_metadata[DIRECT_ASYNC_EVIDENCE_KEY_V1]
    )
    assert evidence.returned_frames == 65
    assert evidence.segment_count == 2
    assert evidence.counter_missing_sample_count == 64 * frame_samples
    assert evidence.inter_segment_skipped_samples == 0


def test_native_bandwidth_capture_selects_exact_radio_configuration(tmp_path: Path) -> None:
    class ExactConfigurationRadio(FakeRadioSource):
        def configure(self, settings: RadioSettingsV1) -> RadioSettingsV1:
            raise AssertionError("ordinary configuration must not serve exact RF geometry")

        def configure_exact(self, settings: RadioSettingsV1) -> RadioSettingsV1:
            self.lifecycle.append("configure_exact")
            return super().configure(settings)

    coordinator = _device_axis_coordinator(tmp_path)
    radios = {
        "radio-a": ExactConfigurationRadio("radio-a"),
        "radio-b": ExactConfigurationRadio("radio-b"),
    }

    result = coordinator.capture_once(
        _mixed_rate_plan(5_000_000),
        radios,
        session_id="mixed-exact-rf-configuration",
    )

    assert result.state is CaptureState.COMMITTED
    assert all("configure_exact" in radio.lifecycle for radio in radios.values())


def test_mixed_rate_capture_rejects_even_one_hz_of_rf_readback_drift(
    tmp_path: Path,
) -> None:
    class ShiftedReadbackRadio(FakeRadioSource):
        def configure(self, settings: RadioSettingsV1) -> RadioSettingsV1:
            super().configure(settings)
            return settings.model_copy(
                update={"center_frequency_hz": settings.center_frequency_hz + 1}
            )

    coordinator = _device_axis_coordinator(tmp_path)
    result = coordinator.capture_once(
        _mixed_rate_plan(10_000_000),
        {
            "radio-a": FakeRadioSource("radio-a"),
            "radio-b": ShiftedReadbackRadio("radio-b"),
        },
        session_id="mixed-rf-readback-drift",
    )

    assert result.state is CaptureState.FAILED
    assert result.bundle is None
    assert any("center_frequency_hz readback mismatch" in error for error in result.errors)
    assert not coordinator.store.reconcile().committed
