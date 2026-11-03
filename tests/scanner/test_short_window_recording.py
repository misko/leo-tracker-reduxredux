from __future__ import annotations

import json
from dataclasses import asdict, replace
from threading import Event, Thread

import numpy as np
import pytest

from leo.scanner.short_window import (
    ShortWindowAcquisition,
    ShortWindowConfiguration,
    ShortWindowTarget,
)
from leo.scanner.short_window_recording import json_metadata, run_short_window_recording
from leo.storage.short_window import ShortWindowReader, ShortWindowWriter


def config(**changes) -> ShortWindowConfiguration:
    return replace(
        ShortWindowConfiguration(
            targets=tuple(
                ShortWindowTarget(f"if-{index}", 1_000_000_000 + index) for index in range(4)
            ),
            max_visits=4,
        ),
        **changes,
    )


class FakeSource:
    def __init__(self):
        self.closed = False
        self.visits = []
        self.configuration = None

    def configure_once(self, configuration):
        self.configuration = configuration

    def capture(self, target, sample_count):
        self.visits.append(target)
        return ShortWindowAcquisition(
            samples=np.full((sample_count, 2, 2), len(self.visits), dtype="<i2"),
            requested_if_center_hz=target.if_center_hz,
            actual_if_center_hz=target.if_center_hz,
            sample_start=(len(self.visits) - 1) * sample_count,
            counter_authority="software_delivery_ordinal",
            validity_authority="provider_attested",
        )

    def close(self):
        self.closed = True


class FakeSink:
    def __init__(self):
        self.windows = []
        self.finish_calls = []
        self.aborted = False

    def append(self, **window):
        self.windows.append(window)

    def finish(self, **terminal):
        self.finish_calls.append(terminal)
        return "fake-publication"

    def abort(self):
        self.aborted = True


def test_records_quiet_and_active_windows_before_finalize_with_immediate_power(tmp_path):
    configuration = config(max_visits=5, threshold_dbfs=-90)
    source = FakeSource()
    sink = ShortWindowWriter(
        tmp_path,
        "roundtrip",
        configuration=json_metadata(asdict(configuration)),
        radio={"serial": "fake"},
        receiver_ids=(0, 1),
        chunk_windows=2,
    )
    updates = []
    result = run_short_window_recording(source, configuration, sink, on_progress=updates.append)
    assert result.status == "complete"
    assert result.stop_reason == "max_visits"
    assert source.closed
    assert source.visits == [*configuration.targets, configuration.targets[0]]
    reader = ShortWindowReader(result.publication)
    windows = list(reader.windows())
    assert reader.manifest.status == "complete"
    assert len(windows) == 5
    for index, window in enumerate(windows):
        assert window.samples.tobytes() == np.full((50_000, 2, 2), index + 1, dtype="<i2").tobytes()
        assert window.index.acquisition["sample_count"] == 50_000
        assert window.index.acquisition["sample_end"] == (index + 1) * 50_000
        assert window.index.acquisition["classification_elapsed_ns"] >= 0
        assert window.index.acquisition["sample_start_utc_ns"] is None
    assert updates[0]["state"] == "capture_complete"
    assert updates[1]["state"] == "writer_accepted"
    assert "samples" not in updates[0]["acquisition"]
    json.dumps(updates, allow_nan=False)
    assert {update["powers"][0]["decision"] for update in updates if "powers" in update} == {
        "active",
        "quiet",
    }


def test_power_emission_precedes_writer_admission():
    sink = FakeSink()
    first_power_emitted = False

    def progress(update):
        nonlocal first_power_emitted
        if update["state"] == "capture_complete" and update["sequence"] == 0:
            assert sink.windows == []
            first_power_emitted = True

    result = run_short_window_recording(
        FakeSource(), config(max_visits=1), sink, on_progress=progress
    )
    assert first_power_emitted
    assert result.written_windows == 1


@pytest.mark.parametrize("by_bytes", [False, True])
def test_writer_overload_stops_new_visits_and_finalizes_accepted_data(by_bytes):
    entered = Event()
    release = Event()
    sink = FakeSink()
    append = sink.append

    def delayed(**window):
        entered.set()
        assert release.wait(2)
        append(**window)

    sink.append = delayed

    def progress(update):
        if update["state"] == "writer_accepted":
            assert entered.wait(1)
        elif update["state"] == "capture_complete" and update["sequence"] == 1:
            # Release only after the second capture has tried admission.
            Thread(target=lambda: (Event().wait(0.05), release.set()), daemon=True).start()

    source = FakeSource()
    result = run_short_window_recording(
        source,
        config(max_visits=20),
        sink,
        on_progress=progress,
        queue_windows=32 if by_bytes else 1,
        queue_bytes=400_000 if by_bytes else 12_800_000,
    )
    assert source.closed
    assert result.status == "incomplete"
    assert result.stop_reason == "writer_overload"
    assert (result.captured_windows, result.accepted_windows, result.written_windows) == (2, 1, 1)
    assert result.queued_peak_windows == 1
    assert result.queued_peak_bytes == 400_000
    assert sink.finish_calls[0]["failure"] is not None


@pytest.mark.parametrize("actual_count", [0, 123])
def test_partial_window_keeps_exact_payload_and_stops_with_incomplete_manifest(
    tmp_path, actual_count
):
    configuration = config()
    source = FakeSource()
    capture = source.capture
    source.capture = lambda target, count: capture(target, actual_count)
    sink = ShortWindowWriter(
        tmp_path,
        "partial",
        configuration=json_metadata(asdict(configuration)),
        radio={},
        receiver_ids=(0, 1),
    )
    result = run_short_window_recording(source, configuration, sink)
    reader = ShortWindowReader(result.publication)
    window = next(reader.windows())
    assert result.status == "incomplete"
    assert result.stop_reason == "capture_integrity_failure"
    assert reader.manifest.status == "incomplete"
    assert window.samples.shape == (actual_count, 2, 2)
    assert window.index.powers[0]["decision"] == "unknown"
    assert result.captured_windows == 1


def test_source_failure_and_close_failure_preserve_both_reasons_and_finalize():
    source = FakeSource()
    sink = FakeSink()

    def fail_capture(*_args):
        raise RuntimeError("retune failed")

    def fail_close():
        raise RuntimeError("restoration failed")

    source.capture = fail_capture
    source.close = fail_close
    result = run_short_window_recording(source, config(), sink)
    assert result.status == "incomplete"
    assert "retune failed" in result.failure
    assert "restoration failed" in result.failure
    assert len(sink.finish_calls) == 1
    assert "restoration failed" in sink.finish_calls[0]["failure"]


def test_configuration_failure_closes_source_and_publishes_zero_window_failure():
    source = FakeSource()
    sink = FakeSink()
    source.configure_once = lambda _: (_ for _ in ()).throw(RuntimeError("configuration failed"))
    result = run_short_window_recording(source, config(), sink)
    assert source.closed
    assert result.status == "incomplete"
    assert result.accepted_windows == 0
    assert sink.finish_calls[0]["stop_reason"] == "source_failure"


def test_disk_full_cannot_publish_complete_and_cleanup_error_is_retained():
    sink = FakeSink()
    sink.append = lambda **_: (_ for _ in ()).throw(OSError("ENOSPC"))
    sink.finish = lambda **_: (_ for _ in ()).throw(OSError("finalization failed"))
    source = FakeSource()
    result = run_short_window_recording(source, config(max_visits=1), sink)
    assert result.status == "incomplete"
    assert "ENOSPC" in result.failure
    assert "finalization failed" in result.failure
    assert result.publication is None
    assert sink.aborted
    assert source.closed


def test_writer_shutdown_has_a_bound_and_terminal_failure_has_reserved_capacity():
    sink = FakeSink()
    release = Event()
    entered = Event()
    append = sink.append

    def stalled(**window):
        entered.set()
        assert release.wait(2)
        append(**window)

    sink.append = stalled
    result = run_short_window_recording(
        FakeSource(), config(max_visits=1), sink, shutdown_timeout_seconds=0.01
    )
    assert entered.is_set()
    assert result.status == "incomplete"
    assert result.stop_reason == "writer_shutdown_timeout"
    assert result.publication is None
    release.set()


def test_cancellation_interrupts_blocking_source_and_closes_it():
    cancel = Event()
    entered = Event()
    interrupted = Event()
    source = FakeSource()
    sink = FakeSink()

    def capture(*_args):
        entered.set()
        assert interrupted.wait(1)
        raise RuntimeError("read cancelled")

    source.capture = capture
    source.cancel = interrupted.set
    Thread(target=lambda: (entered.wait(1), cancel.set()), daemon=True).start()
    result = run_short_window_recording(source, config(), sink, cancellation=cancel)
    assert interrupted.is_set()
    assert source.closed
    assert result.stop_reason == "cancelled"
    assert result.status == "incomplete"


def test_deadline_interrupts_blocking_source():
    interrupted = Event()
    source = FakeSource()
    source.cancel = interrupted.set

    def capture(*_args):
        assert interrupted.wait(1)
        raise RuntimeError("deadline cancelled read")

    source.capture = capture
    result = run_short_window_recording(source, config(duration_seconds=0.04), FakeSink())
    assert interrupted.is_set()
    assert source.closed
    assert result.status == "incomplete"
    assert result.elapsed_seconds < 1


def test_profile_preparation_does_not_consume_capture_duration():
    source = FakeSource()

    def prepare(configuration):
        Event().wait(0.05)
        source.configuration = configuration

    source.configure_once = prepare
    result = run_short_window_recording(
        source, config(duration_seconds=0.025, max_visits=1), FakeSink()
    )
    assert result.status == "complete"
    assert result.captured_windows == 1


def test_firmware_delivery_grace_drains_final_windows_without_extra_admission():
    source = FakeSource()
    configuration = config(duration_seconds=0.02, max_visits=5)
    queued = iter(configuration.targets[:1])

    def next_capture():
        target = next(queued)
        Event().wait(0.05)
        return target, source.capture(target, 50_000)

    source.next_capture = next_capture
    result = run_short_window_recording(
        source, configuration, FakeSink(), provider_duration_grace_seconds=0.1
    )
    assert result.status == "complete"
    assert result.stop_reason == "provider_complete"
    assert result.captured_windows == 1


def test_restoration_shutdown_is_bounded_and_never_reported_successful():
    source = FakeSource()
    release = Event()
    source.close = lambda: release.wait(1)
    result = run_short_window_recording(
        source, config(max_visits=1), FakeSink(), shutdown_timeout_seconds=0.02
    )
    release.set()
    assert result.status == "incomplete"
    assert result.stop_reason == "source_close_timeout"
    assert "restoration" in result.failure


def test_firmware_scheduling_retains_actual_target_order_without_host_filtering():
    source = FakeSource()
    sink = FakeSink()
    configuration = config(policy_id="firmware-weighted-20ms-v1", max_visits=10)
    order = [configuration.targets[index] for index in (2, 2, 3, 0, 1)]
    queued = iter(order)

    def next_capture():
        target = next(queued)
        return target, source.capture(target, 50_000)

    source.next_capture = next_capture
    result = run_short_window_recording(source, configuration, sink)
    assert result.status == "complete"
    assert result.stop_reason == "provider_complete"
    assert [window["target_id"] for window in sink.windows] == [
        target.target_id for target in order
    ]


def test_provider_cannot_emit_unconfigured_target():
    source = FakeSource()
    target = ShortWindowTarget("wrong", 9_000_000_000)
    source.next_capture = lambda: (target, source.capture(target, 50_000))
    result = run_short_window_recording(source, config(), FakeSink())
    assert result.status == "incomplete"
    assert "outside the configured" in result.failure


def test_diagnostic_validity_retains_all_complete_unknown_visits():
    source = FakeSource()
    capture = source.capture
    source.capture = lambda target, count: replace(
        capture(target, count), validity_authority="diagnostic_host_guard"
    )
    sink = FakeSink()
    result = run_short_window_recording(source, config(), sink)
    assert result.status == "complete"
    assert len(sink.windows) == 4
    assert all(window["powers"][0]["decision"] == "unknown" for window in sink.windows)
