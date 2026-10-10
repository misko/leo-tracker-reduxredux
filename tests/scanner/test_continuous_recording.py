from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from threading import Event
from types import SimpleNamespace

import numpy as np
import pytest

from leo.scanner.continuous_recording import run_continuous_recording
from leo.scanner.continuous_window import ContinuousWindow, ContinuousWindowConfiguration
from leo.scanner.short_window import (
    CounterAuthority,
    ShortWindowAcquisition,
    ShortWindowTarget,
    ValidityAuthority,
)
from leo.storage.continuous_window import ContinuousWindowWriter
from leo.storage.short_window import ShortWindowReader


def configuration(**overrides) -> ContinuousWindowConfiguration:
    return ContinuousWindowConfiguration(
        targets=tuple(
            ShortWindowTarget(f"target-{index}", 1_800_000_000 + 10_000_000 * index)
            for index in range(8)
        ),
        segment_windows=8,
        chunk_windows=4,
        **overrides,
    )


class Source:
    identity = (3, 4)

    def __init__(self, count=19, invalid=None, close_error=False):
        self.count = count
        self.invalid = invalid
        self.close_error = close_error
        self.visits = 0
        self.preparations = 0
        self.stop_requests = []

    def configure_once(self, config):
        self.config = config
        self.preparations += 1

    def next_window(self):
        if self.visits == self.count:
            raise StopIteration
        index = self.visits
        self.visits += 1
        count = 100 if index == self.invalid else 50000
        acquisition = ShortWindowAcquisition(
            np.zeros((count, 2, 2), dtype="<i2"),
            self.config.targets[index % 8].if_center_hz,
            self.config.targets[index % 8].if_center_hz,
            generation=4,
            sample_start=(1 << 32) - 25000 + index * 100000,
            counter_authority=CounterAuthority.HARDWARE,
            validity_authority=ValidityAuthority.PROVIDER_ATTESTED,
            quality_flags=("provider_cancelled",) if count != 50000 else (),
        )
        return ContinuousWindow(
            self.config.targets[index % 8], acquisition, 3, 4, index, index // 8, index % 8
        )

    def request_stop(self, forced=False):
        self.stop_requests.append(forced)
        return None

    def close(self):
        if self.close_error:
            raise RuntimeError("injected restoration failure")
        return SimpleNamespace(
            terminal=SimpleNamespace(state=SimpleNamespace(name="COMPLETED"), error=0),
            restoration={"restored": True},
        )


def test_rotation_preserves_all_quiet_iq_global_order_and_counter_wrap(tmp_path: Path):
    config = configuration()
    source = Source()
    sink = ContinuousWindowWriter(tmp_path, "rotation", config, radio={"provider": "fixture"})
    progress = []
    result = run_continuous_recording(source, config, sink, on_progress=progress.append)
    assert result.fault is None
    assert result.captured_windows == result.accepted_windows == result.written_windows == 19
    assert source.preparations == 1
    assert sink.segment_index == 3 and sink.durable_windows == 19
    rows = []
    for index in range(3):
        reader = ShortWindowReader(tmp_path / f"rotation-segment-{index:08d}")
        windows = list(reader.windows())
        assert [window.index.sequence for window in windows] == list(range(len(windows)))
        assert reader.manifest.status == "complete"
        rows.extend(windows)
    assert [window.index.acquisition["global_visit"] for window in rows] == list(range(19))
    assert [window.index.target_id for window in rows] == [
        f"target-{index % 8}" for index in range(19)
    ]
    assert all(power["decision"] == "quiet" for window in rows for power in window.index.powers)
    assert rows[0].index.acquisition["sample_start"] < 1 << 32
    assert rows[1].index.acquisition["sample_start"] > 1 << 32
    assert all(not window.samples.any() for window in rows)
    assert result.peak_queue_windows <= 32 and result.peak_queue_bytes <= 12800000


def test_partial_is_saved_and_restoration_failures_never_publish_complete(tmp_path: Path):
    config = configuration()
    source = Source(count=2, invalid=1, close_error=True)
    sink = ContinuousWindowWriter(tmp_path, "partial", config, radio={})
    result = run_continuous_recording(source, config, sink)
    assert "partial support" in result.fault and "restoration failure" in result.fault
    assert source.stop_requests == [True]
    reader = ShortWindowReader(tmp_path / "partial-segment-00000000")
    assert reader.manifest.status == "incomplete"
    rows = list(reader.windows())
    assert [row.index.sample_count for row in rows] == [50000, 100]
    assert all(power["decision"] == "unknown" for power in rows[1].index.powers)


def test_cancel_before_preparation_does_not_open_source(tmp_path: Path):
    config = configuration()
    stop = Event()
    stop.set()
    source = Source()
    sink = ContinuousWindowWriter(tmp_path, "cancelled", config, radio={})
    result = run_continuous_recording(source, config, sink, stop=stop)
    assert source.preparations == 0
    assert "cancelled before preparation" in result.fault
    assert not list(tmp_path.glob("cancelled-segment-*"))


def test_exhausted_reserve_fault_preserves_existing_segments(tmp_path: Path, monkeypatch):
    config = configuration()
    source = Source(count=1)
    monkeypatch.setattr(
        "leo.storage.continuous_window.shutil.disk_usage", lambda _path: SimpleNamespace(free=0)
    )
    sink = ContinuousWindowWriter(tmp_path, "full", config, radio={})
    result = run_continuous_recording(source, config, sink)
    assert "reserve exhausted" in result.fault
    assert result.written_windows == 0 and source.stop_requests == [True]
    assert sink.durable_windows == 0


def test_continuous_configuration_preserves_old_finite_meaning():
    config = configuration()
    assert config.policy_id == "ordered-continuous-20ms-v1"
    assert config.power_configuration().duration_seconds == 120
    with pytest.raises(ValueError):
        replace(config, targets=config.targets[:7])
    with pytest.raises(ValueError):
        replace(config, reserve_bytes=0)


def test_stuck_source_close_is_bounded_and_never_attests_restoration(tmp_path):
    config = configuration()
    source = Source(count=1)
    release = Event()
    source.close = lambda: release.wait(2)
    sink = ContinuousWindowWriter(tmp_path, "stuck", config, radio={})
    try:
        result = run_continuous_recording(source, config, sink, shutdown_timeout_seconds=0.05)
        assert "restoration remain unattested" in result.fault
        assert result.terminal is None and result.restoration is None
    finally:
        release.set()


@pytest.mark.parametrize("internal_fault", [False, True])
def test_failed_stop_rpc_arms_bounded_drain_for_external_and_internal_fault(
    tmp_path, internal_fault
):
    import time

    config = configuration()

    class Unstoppable(Source):
        def next_window(self):
            time.sleep(0.002)
            return super().next_window()

        def request_stop(self, forced=False):
            self.stop_requests.append(forced)
            raise RuntimeError("STOP RPC unavailable")

        def abort_read(self):
            self.aborted = True

    source = Unstoppable(count=10000, invalid=0 if internal_fault else None)
    source.aborted = False
    sink = ContinuousWindowWriter(tmp_path, "unstoppable", config, radio={})
    result = run_continuous_recording(
        source,
        config,
        sink,
        stop_after_seconds=None if internal_fault else 0.01,
        shutdown_timeout_seconds=0.05,
    )
    assert source.aborted and source.visits < 10000
    assert "STOP" in result.fault and "drain" in result.fault
    assert True in source.stop_requests


def test_repeated_invalid_support_keeps_fault_text_bounded(tmp_path):
    from dataclasses import replace

    config = configuration()

    class Invalid(Source):
        def next_window(self):
            value = super().next_window()
            return replace(
                value,
                acquisition=replace(value.acquisition, quality_flags=("provider_layout_invalid",)),
            )

        def request_stop(self, forced=False):
            raise RuntimeError("unavailable:" + "x" * 10000)

    sink = ContinuousWindowWriter(tmp_path, "diagnostics", config, radio={})
    result = run_continuous_recording(Invalid(count=12), config, sink)
    assert len(result.fault) < 4096 and "additional errors" in result.fault


def test_complete_adc12_clipping_stays_unknown_and_recorded_without_stop(tmp_path):
    from dataclasses import replace

    config = configuration()

    class Clipped(Source):
        def next_window(self):
            value = super().next_window()
            return replace(
                value, acquisition=replace(value.acquisition, quality_flags=("adc12_clipping",))
            )

    source = Clipped(count=3)
    sink = ContinuousWindowWriter(tmp_path, "clipped", config, radio={})
    result = run_continuous_recording(source, config, sink)
    assert result.fault is None and source.stop_requests == []
    windows = list(ShortWindowReader(tmp_path / "clipped-segment-00000000").windows())
    assert len(windows) == 3
    assert all(power["decision"] == "unknown" for row in windows for power in row.index.powers)


def test_blocking_internal_stop_rpc_does_not_block_capture_shutdown(tmp_path):
    import time

    config = configuration()
    release = Event()

    class Blocked(Source):
        def next_window(self):
            time.sleep(0.001)
            return super().next_window()

        def request_stop(self, forced=False):
            self.stop_requests.append(forced)
            release.wait(2)

        def abort_read(self):
            self.aborted = True

    source = Blocked(count=10000, invalid=0)
    source.aborted = False
    sink = ContinuousWindowWriter(tmp_path, "blocked-control", config, radio={})
    started = time.monotonic()
    try:
        result = run_continuous_recording(source, config, sink, shutdown_timeout_seconds=0.05)
        assert time.monotonic() - started < 1
        assert source.aborted and source.stop_requests == [True]
        assert "STOP RPC exceeded" in result.fault
    finally:
        release.set()


def test_control_thread_publication_cannot_be_joined_before_start(tmp_path,monkeypatch):
    import threading

    from leo.scanner import continuous_recording as recording
    real_thread = threading.Thread
    starting = Event()
    permit_start = Event()
    ended = Event()
    errors = []
    results = []
    class DelayedStart(real_thread):
        def start(self):
            if self.name == "continuous-stop-control":
                starting.set()
                assert permit_start.wait(2)
            super().start()
    monkeypatch.setattr(recording,"Thread",DelayedStart)
    class SourceWithBarrier(Source):
        def next_window(self):
            if self.visits == 1:
                assert starting.wait(1)
                raise StopIteration
            return super().next_window()
    class BrokenSink:
        def append(self,**_): raise OSError("writer failure forces STOP publication")
        def finish(self,**_): return {}
        def abort(self): pass
    def run():
        try:
            results.append(run_continuous_recording(SourceWithBarrier(count=1),configuration(),BrokenSink()))
        except BaseException as error:
            errors.append(error)
        finally:
            ended.set()
    worker = real_thread(target=run)
    worker.start()
    try:
        assert starting.wait(1)
        assert not ended.wait(0.15)  # Main must wait for atomic thread startup.
        assert not errors
    finally:
        permit_start.set()
        worker.join(2)
    assert ended.is_set() and not errors and "writer failure" in results[0].fault
