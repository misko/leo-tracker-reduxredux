from __future__ import annotations

from threading import Event

import pytest

from leo.storage.adaptive_hop import AdaptiveHopIqStore
from leo.storage.adaptive_hop_queue import QueuedAdaptiveHopSessionWriter
from leo.storage.errors import BundleStateError
from tests.scanner.adaptive_hop_fixtures import block_fixture, receipt_fixture, timing_fixture


@pytest.mark.parametrize("rate", [2_500_000, 5_000_000])
def test_adaptive_queued_writer_drains_all_owned_iq(tmp_path, rate):
    receipt = receipt_fixture(rate=rate, count=10)
    store = AdaptiveHopIqStore(tmp_path)
    writer = store.begin_queued(receipt.session_id, receipt.plan, capacity_visits=16)
    for index in range(receipt.complete_visit_count):
        writer.append(block_fixture(receipt, index))
    published = writer.finish(receipt, timing=timing_fixture(receipt))
    assert store.verify(receipt.session_id) == published
    assert writer.telemetry.enqueue_failure_count == 0
    assert 0 < writer.telemetry.high_water_visits <= 16
    assert writer.telemetry.maximum_writer_service_ns > 0
    assert not writer._thread.is_alive()
    writer.abort()
    store.close()


class BlockedWriter:
    def __init__(self, *, fail=False):
        self.entered = Event()
        self.release = Event()
        self.aborted = False
        self.fail = fail

    def append(self, _block):
        self.entered.set()
        assert self.release.wait(3)
        if self.fail:
            raise OSError("injected storage error")

    def abort(self):
        assert self.release.is_set(), "must not close a file in use by the worker"
        self.aborted = True


@pytest.mark.parametrize("fault", ["full", "worker", "timeout"])
def test_adaptive_queue_faults_never_block_capture_or_publish(monkeypatch, fault):
    receipt = receipt_fixture(count=2)
    base = BlockedWriter(fail=fault == "worker")
    writer = QueuedAdaptiveHopSessionWriter(base, capacity_visits=1)
    block = block_fixture(receipt, 0)
    writer.append(block)
    assert base.entered.wait(1)
    try:
        if fault == "full":
            writer.append(block)
            with pytest.raises(BundleStateError, match="exhausted"):
                writer.append(block)
            assert writer.telemetry.enqueue_failure_count == 1
        elif fault == "timeout":
            monkeypatch.setattr("leo.storage.adaptive_hop_queue._JOIN_SECONDS", 0.01)
            with pytest.raises(BundleStateError, match="did not stop"):
                writer.finish(receipt, timing=timing_fixture(receipt))
            assert not base.aborted
            monkeypatch.setattr("leo.storage.adaptive_hop_queue._JOIN_SECONDS", 2)
    finally:
        base.release.set()
    with pytest.raises(BundleStateError):
        writer.finish(receipt, timing=timing_fixture(receipt))
    try:
        writer.abort()
    except BundleStateError:
        assert fault == "worker"
    assert base.aborted
    assert not writer._thread.is_alive()


def test_adaptive_invalid_queue_capacity_does_not_reserve_storage(tmp_path):
    store = AdaptiveHopIqStore(tmp_path)
    receipt = receipt_fixture(count=0)
    for capacity in (0, True, 65, 1.0):
        with pytest.raises(ValueError):
            store.begin_queued(receipt.session_id, receipt.plan, capacity_visits=capacity)
    assert list(tmp_path.iterdir()) == []
    store.close()
