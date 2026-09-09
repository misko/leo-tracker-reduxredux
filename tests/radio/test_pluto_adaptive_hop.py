"""Concrete adapter ownership and actual-visit evidence; no radio connections."""

import dataclasses
from threading import Event, get_ident

import numpy as np
import pytest

from leo.radio import pluto_adaptive_hop as module
from leo.radio.adaptive_hop_mapping import map_adaptive_capture
from leo.radio.pluto_adaptive_hop import PlutoAdaptiveHopError, PlutoAdaptiveHopRadio
from leo.radio.scanner_glrt_metadata import ScannerAdaptiveGlrtMetadataExtension, ScannerGlrtOptions
from leo.scanner.ports import ScanRadioIdentity
from leo.storage.adaptive_hop import AdaptiveHopIqStore
from leo.storage.adaptive_hop_capture import capture_adaptive_hop_to_store
from tests.radio.adaptive_hop_fixtures import Client, UpstreamSession
from tests.scanner.adaptive_hop_fixtures import block_fixture, receipt_fixture

OPTIONS = ScannerGlrtOptions("a" * 64, "b" * 64, mode="positive-only-v1")


def radio_fixture(upstream, **kwargs):
    client = Client(upstream)
    calls = []

    def factory(uri, serial, *, metadata_extension):
        calls.append((uri, serial, metadata_extension))
        return client

    radio = PlutoAdaptiveHopRadio(
        "192.168.1.14",
        expected_serial="synthetic-only",
        radio_id="synthetic",
        scanner_glrt=OPTIONS,
        client_factory=factory,
        **kwargs,
    )
    return radio, client, calls


@pytest.mark.parametrize("rate", [2_500_000, 5_000_000])
@pytest.mark.parametrize("mode", ["shadow", "adaptive"])
def test_concrete_adapter_to_queued_store_preserves_actual_visits_and_terminal_iq(
    tmp_path, rate, mode
):
    receipt = receipt_fixture(rate=rate, mode=mode, count=31)
    upstream = UpstreamSession(receipt)
    radio, client, calls = radio_fixture(upstream)
    store = AdaptiveHopIqStore(tmp_path)
    barriers = []

    def barrier():
        assert upstream.closed
        assert radio.classification_evidence is not None
        barriers.append("closed")

    result = capture_adaptive_hop_to_store(
        radio,
        receipt.plan,
        session_id=receipt.session_id,
        store=store,
        cancel=Event(),
        before_publish=barrier,
        queue_capacity_visits=64,  # entire accelerated fixture fits; not an ARM load test
    )
    assert barriers == ["closed"]
    assert result.manifest.receipt == receipt
    assert store.verify(receipt.session_id) == result
    assert client.arguments[1] == receipt.terminal.session_id
    assert client.arguments[2].generation == receipt.plan.policy.generation
    assert isinstance(calls[0][2], ScannerAdaptiveGlrtMetadataExtension)
    assert calls[0][2].generation == receipt.plan.policy.generation
    assert calls[0][:2] == (receipt.radio_uri, receipt.radio_serial)
    assert len(set(upstream.threads)) == 1
    assert upstream.threads[0] != get_ident()
    with store.reader(receipt.session_id) as reader:
        last = receipt.complete_visit_count - 1
        expected = block_fixture(receipt, last).samples
        _visit, iq = reader.read_visit_ci16(last)
        np.testing.assert_array_equal(iq[..., 0], expected.real)
        np.testing.assert_array_equal(iq[..., 1], expected.imag)
    assert radio.classification_evidence is not None
    assert not radio.classification_evidence.delivery_complete  # fake did not negotiate
    assert radio.classification_error is not None
    radio.close()  # idempotent; no second upstream ownership episode
    store.close()


@pytest.mark.parametrize("count", [0, 1, 3])
def test_empty_or_short_cancel_can_be_closed_without_consuming_iq(count):
    receipt = receipt_fixture(count=count)
    upstream = UpstreamSession(receipt)
    radio, _, _ = radio_fixture(upstream, read_ahead_visits=1)
    radio.open()
    session = radio.begin_session(receipt.plan, session_id=receipt.session_id)
    session.request_cancel()
    assert session.finish() == receipt
    radio.close()
    assert upstream.closed
    assert session.complete


def test_cancellation_drains_read_ahead_and_upstream_pending_iq():
    receipt = receipt_fixture(count=5)
    pulled = Event()
    release = Event()

    class Held(UpstreamSession):
        def visits(self):
            pulled.set()
            assert release.wait(3)
            yield from super().visits()

    upstream = Held(receipt, terminal_visits=2)
    radio, _, _ = radio_fixture(upstream, read_ahead_visits=1)
    radio.open()
    session = radio.begin_session(receipt.plan, session_id=receipt.session_id)
    assert pulled.wait(3)
    session.request_cancel()
    release.set()
    blocks = []
    while not session.complete:
        try:
            blocks.append(session.read_visit())
        except StopIteration:
            break
    assert tuple(b.evidence for b in blocks) == receipt.visits
    assert session.finish() == receipt
    radio.close()
    assert len(set(upstream.threads)) == 1


@pytest.mark.parametrize("mutation", ["identity", "inventory", "iq", "order", "restore"])
def test_corrupt_source_is_failure_and_cleans_up(tmp_path, mutation):
    receipt = receipt_fixture(count=3)
    upstream = UpstreamSession(receipt, terminal_visits=0)
    if mutation == "identity":
        upstream.receipt = dataclasses.replace(upstream.receipt, radio_serial="different")
    elif mutation == "inventory":
        upstream.receipt = dataclasses.replace(
            upstream.receipt, stream=dataclasses.replace(upstream.receipt.stream, visits=())
        )
    elif mutation == "restore":
        upstream.receipt = dataclasses.replace(upstream.receipt, host_lifecycle=None)
    elif mutation == "iq":
        upstream.sampled = lambda index: type(
            "Bad",
            (),
            {
                "visit": upstream.receipt.stream.visits[index],
                "samples": np.zeros((2, 1)),
            },
        )()
    else:
        original = upstream.sampled
        upstream.sampled = lambda index: original(1 - index)
    radio, _, _ = radio_fixture(upstream)
    store = AdaptiveHopIqStore(tmp_path)
    with pytest.raises(Exception, match="adaptive capture failed"):
        capture_adaptive_hop_to_store(
            radio,
            receipt.plan,
            session_id=receipt.session_id,
            store=store,
            cancel=Event(),
        )
    assert upstream.closed
    assert store.session_ids() == ()
    assert radio.classification_error is not None
    store.close()


def test_thread_start_failure_closes_new_upstream(monkeypatch):
    receipt = receipt_fixture(count=0)
    upstream = UpstreamSession(receipt)
    radio, _, _ = radio_fixture(upstream)
    radio.open()

    def fail(_):
        raise RuntimeError("cannot start producer")

    monkeypatch.setattr(module.threading.Thread, "start", fail)
    with pytest.raises(PlutoAdaptiveHopError, match="cannot start producer"):
        radio.begin_session(receipt.plan, session_id=receipt.session_id)
    assert upstream.closed
    radio.close()


def test_snapshot_failure_does_not_fail_valid_iq(monkeypatch, tmp_path):
    def fail(_):
        raise ValueError("classifier offline")

    monkeypatch.setattr(ScannerAdaptiveGlrtMetadataExtension, "snapshot", fail)
    receipt = receipt_fixture(count=2)
    upstream = UpstreamSession(receipt)
    radio, _, _ = radio_fixture(upstream)
    store = AdaptiveHopIqStore(tmp_path)
    result = capture_adaptive_hop_to_store(
        radio,
        receipt.plan,
        session_id=receipt.session_id,
        store=store,
        cancel=Event(),
    )
    assert result.manifest.receipt == receipt
    assert "classifier offline" in radio.classification_error
    assert radio.classification_evidence is None
    store.close()


def test_timed_out_owner_is_not_closed_concurrently_or_reopened(monkeypatch):
    receipt = receipt_fixture(count=3)
    entered, release = Event(), Event()

    class Held(UpstreamSession):
        def visits(self):
            entered.set()
            assert release.wait(3)
            yield from super().visits()

    upstream = Held(receipt)
    radio, _, _ = radio_fixture(upstream, read_ahead_visits=1)
    radio.open()
    radio.begin_session(receipt.plan, session_id=receipt.session_id)
    assert entered.wait(3)
    monkeypatch.setattr(module, "_JOIN_SECONDS", 0.001)
    try:
        with pytest.raises(PlutoAdaptiveHopError, match="did not stop"):
            radio.close()
        assert not upstream.closed
        with pytest.raises(PlutoAdaptiveHopError, match="already open"):
            radio.open()
    finally:
        monkeypatch.setattr(module, "_JOIN_SECONDS", 3.0)
        release.set()
        radio.close()
    assert upstream.closed
    assert len(set(upstream.threads)) == 1
    assert upstream.threads[0] != get_ident()


def test_unsupported_client_does_not_silently_disable_adaptive_metadata():
    receipt = receipt_fixture(count=0)
    calls = []

    def old_factory(uri, serial):
        calls.append((uri, serial))
        raise AssertionError("unsupported factory body must not run")

    radio = PlutoAdaptiveHopRadio(
        "192.168.1.14",
        expected_serial="synthetic-only",
        radio_id="synthetic",
        scanner_glrt=OPTIONS,
        client_factory=old_factory,
    )
    radio.open()
    with pytest.raises(PlutoAdaptiveHopError, match="metadata_extension"):
        radio.begin_session(receipt.plan, session_id=receipt.session_id)
    radio.close()
    assert calls == []


def test_begin_requires_open_and_one_session():
    receipt = receipt_fixture(count=2)
    radio, _, _ = radio_fixture(UpstreamSession(receipt))
    with pytest.raises(PlutoAdaptiveHopError, match="opened first"):
        radio.begin_session(receipt.plan, session_id=receipt.session_id)
    radio.open()
    with pytest.raises(PlutoAdaptiveHopError, match="already open"):
        radio.open()
    radio.begin_session(receipt.plan, session_id=receipt.session_id)
    with pytest.raises(PlutoAdaptiveHopError, match="already owns"):
        radio.begin_session(receipt.plan, session_id=receipt.session_id)
    radio.close()
    radio.open()
    assert radio.classification_evidence is None
    radio.close()


@pytest.mark.parametrize(
    "changes",
    [
        {"host": "192.168.2.1"},
        {"host": "127.0.0.1"},
        {"host": "ip:192.168.1.14"},
        {"expected_serial": "104000bac4950008230026001b440a003a"},
        {"expected_serial": " "},
        {"radio_id": " "},
        {"read_ahead_visits": 0},
        {"read_ahead_visits": True},
        {"read_ahead_visits": 65},
        {"scanner_glrt": None},
        {"scanner_glrt": dataclasses.replace(OPTIONS, mode="unqualified-evidence")},
    ],
)
def test_admission_rejects_before_client_factory(changes):
    kwargs = dict(
        host="192.168.1.14", expected_serial="synthetic", radio_id="synthetic", scanner_glrt=OPTIONS
    )
    with pytest.raises(ValueError):
        PlutoAdaptiveHopRadio(**(kwargs | changes))


def test_fixture_maps_without_replacing_actual_adapter_validation():
    receipt = receipt_fixture(count=31)
    upstream = UpstreamSession(receipt)
    assert (
        map_adaptive_capture(
            upstream.receipt,
            plan=receipt.plan,
            identity=ScanRadioIdentity(receipt.radio_id, receipt.radio_serial, receipt.radio_uri),
            session_id=receipt.session_id,
        )
        == receipt
    )
