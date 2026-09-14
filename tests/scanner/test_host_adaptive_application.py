from threading import Event

import pytest

from leo.scanner.adaptive_hop_application import (
    AdaptiveHopCaptureError,
    capture_adaptive_hop_session,
    capture_host_adaptive_hop_session,
)
from leo.scanner.single_rx import SingleRxHopTimingV2
from leo.storage.adaptive_hop import AdaptiveHopIqStore, HostAdaptiveHopIqManifestV2
from leo.storage.adaptive_hop_capture import capture_host_adaptive_hop_to_store
from tests.radio.test_pluto_host_adaptive import setup
from tests.scanner.host_adaptive_fixtures import host_receipt
from tests.scanner.test_adaptive_hop_application import FixtureRadio
from tests.storage.test_host_adaptive_hop_store import block


class HostFixtureRadio(FixtureRadio):
    def read_visit(self):
        if self.fault in ("early_stop", "read"):
            return super().read_visit()
        if self.complete:
            raise StopIteration
        value = block(self.receipt, self.index)
        self.index += 1
        return value


@pytest.mark.parametrize("receiver", [0, 1])
@pytest.mark.parametrize("mode", ["shadow", "adaptive"])
def test_host_capture_application_stores_native_iq_after_owned_close(tmp_path, receiver, mode):
    source = host_receipt(receiver=receiver, mode=mode, count=5)
    radio, clients, engines = setup(source)
    store = AdaptiveHopIqStore(tmp_path)
    barriers = []

    def barrier():
        assert clients[0].closed and engines[0].closed
        assert store.session_ids() == ()
        barriers.append(True)

    try:
        published = capture_host_adaptive_hop_to_store(
            radio,
            source.plan,
            session_id=source.session_id,
            store=store,
            cancel=Event(),
            before_publish=barrier,
        )
        assert barriers == [True]
        assert isinstance(published.manifest, HostAdaptiveHopIqManifestV2)
        assert isinstance(published.manifest.timing, SingleRxHopTimingV2)
        assert published.manifest.timing.sample_rate_hz == 10_000_000
        assert (
            published.manifest.timing.session_start_device_sample_counter
            == source.terminal.first_counter
        )
        assert published.manifest.receipt.visits == source.visits
        assert published.manifest.receipt.plan.geometry.receiver_ids == (receiver,)
        assert store.verify(source.session_id) == published
        assert published.manifest.uncompressed_bytes == source.valid_sample_count * 4
    finally:
        store.close()


@pytest.mark.parametrize(
    "fault", ["begin", "read", "early_stop", "finish", "inventory", "identity", "close", "barrier"]
)
def test_host_capture_failure_never_publishes_and_closes_radio(tmp_path, fault):
    source = host_receipt(count=3)
    radio = HostFixtureRadio(source, fault=fault)
    store = AdaptiveHopIqStore(tmp_path)

    def barrier():
        if fault == "barrier":
            raise OSError("synthetic barrier failure")

    try:
        with pytest.raises((AdaptiveHopCaptureError, OSError)):
            capture_host_adaptive_hop_to_store(
                radio,
                source.plan,
                session_id=source.session_id,
                store=store,
                cancel=Event(),
                before_publish=barrier,
            )
        assert radio.log[-1] == "close"
        assert store.session_ids() == ()
    finally:
        store.close()


def test_host_capture_pre_cancel_and_legacy_entry_point_do_not_open_radio():
    source = host_receipt(count=0)
    radio = HostFixtureRadio(source)
    cancel = Event()
    cancel.set()
    with pytest.raises(AdaptiveHopCaptureError, match="before open"):
        capture_host_adaptive_hop_session(
            radio,
            source.plan,
            session_id=source.session_id,
            visit_sink=lambda _: None,
            cancel=cancel,
        )
    with pytest.raises(ValueError):
        capture_adaptive_hop_session(
            radio,
            source.plan,
            session_id=source.session_id,
            visit_sink=lambda _: None,
            cancel=Event(),
        )
    assert radio.log == []


def test_host_capture_sink_failure_retains_validated_terminal_receipt():
    source = host_receipt(count=3)
    radio = HostFixtureRadio(source)

    def sink(_):
        raise OSError("synthetic compression failure")

    with pytest.raises(AdaptiveHopCaptureError) as caught:
        capture_host_adaptive_hop_session(
            radio, source.plan, session_id=source.session_id, visit_sink=sink, cancel=Event()
        )
    assert caught.value.terminal_receipt == source
    assert radio.log[-3:] == ["cancel", "finish", "close"]
