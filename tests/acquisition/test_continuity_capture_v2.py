from __future__ import annotations

import logging
import threading
import time
from decimal import Decimal
from pathlib import Path
from threading import Event

import pytest

from leo.acquisition import AcquisitionConfig, AcquisitionCoordinator
from leo.contracts.profile import (
    CaptureProfileRevisionV1,
    CaptureProfileRevisionV2,
    CaptureProfileV1,
    CaptureProfileV2,
)
from leo.contracts.radio import RadioSettingsV1, ReceiverGainV1
from leo.contracts.recording import (
    CompressionSettingsV1,
    ContinuitySummaryV2,
    RecordingManifestV2,
)
from leo.contracts.states import (
    CaptureState,
    ContinuityPolicy,
    GainMode,
    SourceType,
    StreamState,
    TimingMethod,
)
from leo.domain.iq import IqBlock
from leo.domain.profiles import compile_capture_plan
from leo.processing.continuity import iter_masked_device_iq
from leo.radio.fake import FakeRadioSource
from leo.storage import RecordingStore
from leo.storage import writer as storage_writer
from leo.storage.writer import StreamBundleWriter


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
    queue_type = coordinator_module.queue.Queue

    class PausedAfterGetQueue(queue_type):
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
        _plan(sample_count=4),
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
    started = time.monotonic()

    try:
        result = coordinator.capture_once(
            _plan(sample_count=4),
            {"radio-a": FakeRadioSource("radio-a")},
            session_id=session_id,
        )
    finally:
        release_fsync.set()

    assert entered_fsync.is_set()
    assert time.monotonic() - started < 1.0
    assert result.state is CaptureState.FAILED
    assert result.manifest is None
    assert any("bounded timeout" in error for error in result.errors)
    assert completed_fsync.wait(timeout=1.0)
    deadline = time.monotonic() + 1.0
    while any(thread.name == "leo-store-stream-0" for thread in threading.enumerate()):
        assert time.monotonic() < deadline
        time.sleep(0.01)
    spool = store_root / "spool" / f"{session_id}.partial"
    assert spool.is_dir()
    assert not (spool / "manifest.json").exists()
    assert not list((store_root / "recordings").rglob(session_id))


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
