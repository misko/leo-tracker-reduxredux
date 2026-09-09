from __future__ import annotations

from threading import Event

import pytest

from leo.scanner.adaptive_hop_application import (
    AdaptiveHopCaptureError,
    capture_adaptive_hop_session,
)
from leo.scanner.ports import ScanRadioIdentity
from leo.storage.adaptive_hop import AdaptiveHopIqStore
from leo.storage.adaptive_hop_capture import capture_adaptive_hop_to_store
from tests.scanner.adaptive_hop_fixtures import block_fixture, receipt_fixture


class FixtureRadio:
    def __init__(self, receipt, *, fault=None):
        self.receipt = receipt
        self.plan = receipt.plan
        self.identity = ScanRadioIdentity(receipt.radio_id, receipt.radio_serial, receipt.radio_uri)
        self.fault = fault
        self.log = []
        self.index = 0
        self.start_clock_bracket = None

    def open(self):
        self.log.append("open")
        return self.identity

    def begin_session(self, plan, *, session_id):
        self.log.append("begin")
        assert plan == self.plan and session_id == self.receipt.session_id
        if self.fault == "begin":
            raise OSError("injected begin failure")
        return self

    @property
    def complete(self):
        return self.index == self.receipt.complete_visit_count

    def read_visit(self):
        if self.fault == "early_stop":
            raise StopIteration
        if self.fault == "read":
            raise OSError("injected read failure")
        if self.complete:
            raise StopIteration
        block = block_fixture(self.receipt, self.index)
        self.index += 1
        return block

    def request_cancel(self):
        self.log.append("cancel")

    def finish(self):
        self.log.append("finish")
        if self.fault == "finish":
            raise OSError("injected terminal failure")
        if self.fault == "inventory":
            return self.receipt.model_copy(update={"valid_sample_count": 0})
        if self.fault == "identity":
            return self.receipt.model_copy(update={"radio_serial": "another-radio"})
        return self.receipt

    def close(self):
        self.log.append("close")
        if self.fault == "close":
            raise OSError("injected close failure")


@pytest.mark.parametrize("rate", [2_500_000, 5_000_000])
@pytest.mark.parametrize("mode", ["adaptive", "shadow"])
def test_adaptive_application_real_storage_barrier_and_final_inventory(tmp_path, rate, mode):
    receipt = receipt_fixture(rate=rate, mode=mode, count=30)
    radio = FixtureRadio(receipt)
    store = AdaptiveHopIqStore(tmp_path)

    def barrier():
        assert radio.log[-1] == "close"
        assert store.session_ids() == ()
        radio.log.append("barrier")

    published = capture_adaptive_hop_to_store(
        radio,
        receipt.plan,
        session_id=receipt.session_id,
        store=store,
        cancel=Event(),
        queue_capacity_visits=32,
        before_publish=barrier,
    )
    assert radio.log == ["open", "begin", "finish", "close", "barrier"]
    assert published.manifest.receipt == receipt
    assert published.manifest.queue_telemetry.enqueue_failure_count == 0
    assert store.verify(receipt.session_id) == published
    store.close()


@pytest.mark.parametrize(
    "fault", ["begin", "read", "early_stop", "finish", "inventory", "identity", "close", "barrier"]
)
def test_adaptive_application_failures_cleanup_without_publication(tmp_path, fault):
    receipt = receipt_fixture(count=3)
    radio = FixtureRadio(receipt, fault=fault)
    store = AdaptiveHopIqStore(tmp_path)

    def barrier():
        if fault == "barrier":
            raise OSError("injected external cleanup failure")

    with pytest.raises((AdaptiveHopCaptureError, OSError)):
        capture_adaptive_hop_to_store(
            radio,
            receipt.plan,
            session_id=receipt.session_id,
            store=store,
            cancel=Event(),
            before_publish=barrier,
        )
    assert radio.log[-1] == "close"
    if fault in ("read", "early_stop"):
        assert radio.log[-3:] == ["cancel", "finish", "close"]
    assert store.session_ids() == ()
    store.close()


@pytest.mark.parametrize("failure", [RuntimeError, KeyboardInterrupt])
def test_adaptive_sink_failure_preserves_primary_and_closes_radio(failure):
    receipt = receipt_fixture(count=3)
    radio = FixtureRadio(receipt)

    def sink(_):
        raise failure("injected sink failure")

    with pytest.raises(
        KeyboardInterrupt if failure is KeyboardInterrupt else AdaptiveHopCaptureError
    ):
        capture_adaptive_hop_session(
            radio,
            receipt.plan,
            session_id=receipt.session_id,
            visit_sink=sink,
            cancel=Event(),
        )
    assert radio.log[-3:] == ["cancel", "finish", "close"]


def test_adaptive_pre_cancel_does_not_open_radio():
    receipt = receipt_fixture(count=0)
    radio = FixtureRadio(receipt)
    cancel = Event()
    cancel.set()
    with pytest.raises(AdaptiveHopCaptureError, match="before open"):
        capture_adaptive_hop_session(
            radio,
            receipt.plan,
            session_id=receipt.session_id,
            visit_sink=lambda _: None,
            cancel=cancel,
        )
    assert radio.log == []


@pytest.mark.parametrize("clock_step", [0, 100_000_000])
def test_adaptive_timing_uses_source_counter_and_reports_clock_uncertainty(clock_step):
    receipt = receipt_fixture(count=2)
    radio = FixtureRadio(receipt)
    real = iter((1_000_000_000_000, 1_000_001_000_000, 1_300_000_000_000 + clock_step))
    mono = iter((100_000_000_000, 100_001_000_000, 400_000_000_000))
    capture = capture_adaptive_hop_session(
        radio,
        receipt.plan,
        session_id=receipt.session_id,
        visit_sink=lambda _: None,
        cancel=Event(),
        realtime_ns=lambda: next(real),
        monotonic_ns=lambda: next(mono),
    )
    assert capture.timing.session_start_device_sample_counter == receipt.terminal.first_counter
    assert capture.timing.qualified == (clock_step == 0)
    assert capture.timing.maximum_realtime_monotonic_offset_spread_ns == clock_step
