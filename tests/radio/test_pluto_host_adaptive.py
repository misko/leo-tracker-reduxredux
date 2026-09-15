import threading
import time
from types import SimpleNamespace

import numpy as np
import pytest
from pluto_plus.host_adaptive_hop_stream import HostAdaptiveHopSampledVisitV3

from leo.analysis.host_decision import HostDecisionEvidence
from leo.radio.pluto_host_adaptive import PlutoHostAdaptiveHopRadio
from tests.radio.adaptive_hop_fixtures import upstream_receipt
from tests.scanner.host_adaptive_fixtures import (
    host_receipt,
    multirate_host_receipt,
    multirate_numerics,
    numerics,
)


class Engine:
    def __init__(self, *, rate=10_000_000, delay=0, fail=False):
        self.threads = [threading.get_ident()]
        self.rate, self.delay, self.fail = rate, delay, fail
        self.closed = False

    def run(self, iq, *, edge):
        self.threads.append(threading.get_ident())
        assert iq.dtype == np.dtype("<i2") and iq.shape == (self.rate * 120 // 1000, 2)
        assert not iq.flags.writeable
        assert edge in ("lower", "upper")
        if self.delay:
            time.sleep(self.delay)
        if self.fail:
            raise RuntimeError("synthetic detector failure")
        values = numerics() if self.rate == 10_000_000 else multirate_numerics(self.rate)
        return HostDecisionEvidence(
            **values.model_dump(exclude={"schema_version", "source_rate_hz"})
        )

    def close(self):
        self.threads.append(threading.get_ident())
        self.closed = True


class Client:
    def __init__(self, receipt, *, pacing=0.04, reject=False, clock_brackets=None):
        self.owner = threading.get_ident()
        self.source = receipt
        self.receipt = upstream_receipt(receipt)
        self.closed = False
        self.next_index = 0
        self.feedback = []
        self.pacing, self.reject = pacing, reject
        self.clock_brackets = clock_brackets
        self.calls = []
        self.restoration_delay = 0

    def owned(self, name):
        assert threading.get_ident() == self.owner
        self.calls.append(name)

    def start(
        self,
        plan,
        *,
        policy,
        decision,
        session_id,
        tandem_request,
        direct_async_frames=0,
    ):
        self.owned("start")
        assert plan.receiver_id == decision.receiver_id == self.source.plan.classification_receiver
        assert policy == self.receipt.stream.request.policy
        assert decision == self.receipt.stream.request.decision
        assert session_id == self.source.terminal.session_id
        self.direct_async_frames = direct_async_frames
        return self

    @property
    def start_clock_bracket(self):
        self.owned("clock")
        if self.clock_brackets is None:
            return None
        return self.clock_brackets[min(self.next_index, 1)]

    @property
    def stream_generation(self):
        self.owned("generation")
        return self.source.stream_generation

    def sampled(self):
        index = self.next_index
        self.next_index += 1
        return HostAdaptiveHopSampledVisitV3(
            self.receipt.stream.visits[index],
            np.full(
                (1, self.source.plan.geometry.valid_visit_samples),
                index + 2j,
                np.complex64,
            ),
            self.source.plan.classification_receiver,
        )

    def visits(self, *, before_release=None):
        self.owned("visits")
        while self.next_index < self.source.complete_visit_count:
            if self.pacing:
                time.sleep(self.pacing)
            self.owned("read")
            yield self.sampled()
        self.closed = True
        if before_release is not None:
            before_release()
        time.sleep(self.restoration_delay)

    def submit_feedback(self, feedback):
        self.owned("feedback")
        feedback.pack()
        assert feedback.visit == len(self.feedback)
        if self.reject:
            raise OSError("synthetic provider rejection")
        self.feedback.append(feedback)
        return not self.closed

    def close(self, *, before_release=None):
        self.owned("close")
        self.closed = True
        if before_release is not None:
            before_release()
        return self.receipt

    def take_terminal_visits(self):
        self.owned("terminal")
        assert self.closed
        return tuple(
            self.sampled() for _ in range(self.next_index, self.source.complete_visit_count)
        )


def setup(
    receipt,
    *,
    pacing=0.04,
    reject=False,
    engine_delay=0,
    engine_fail=False,
    read_ahead=8,
    clock_brackets=None,
):
    clients, engines = [], []

    def client_factory(uri, serial):
        assert uri == receipt.radio_uri and serial == receipt.radio_serial
        clients.append(
            Client(
                receipt,
                pacing=pacing,
                reject=reject,
                clock_brackets=clock_brackets,
            )
        )
        return clients[-1]

    def engine_factory():
        engines.append(
            Engine(
                rate=receipt.plan.geometry.sample_rate_hz,
                delay=engine_delay,
                fail=engine_fail,
            )
        )
        return engines[-1]

    radio = PlutoHostAdaptiveHopRadio(
        "192.168.1.14",
        expected_serial=receipt.radio_serial,
        radio_id=receipt.radio_id,
        decision=receipt.plan.decision,
        decision_engine_factory=engine_factory,
        client_factory=client_factory,
        read_ahead_visits=read_ahead,
    )
    return radio, clients, engines


def drain(session):
    visits = []
    while True:
        try:
            block = session.read_visit()
        except StopIteration:
            break
        visits.append(block.evidence)
    return visits


@pytest.mark.parametrize("receiver", [0, 1])
@pytest.mark.parametrize("mode", ["shadow", "adaptive"])
def test_client_construction_admission_iio_and_feedback_have_one_owner(receiver, mode):
    receipt = host_receipt(receiver=receiver, mode=mode, count=7)
    radio, clients, engines = setup(receipt)
    consumer_thread = threading.get_ident()
    assert radio.open() == radio.identity
    try:
        session = radio.begin_session(receipt.plan, session_id=receipt.session_id)
        assert session.start_clock_bracket is None
        assert tuple(drain(session)) == receipt.visits
        result = session.finish()
        assert result.plan == receipt.plan and result.visits == receipt.visits
        assert len(result.host_decisions) == receipt.complete_visit_count
        assert all(d.health == "healthy" for d in result.host_decisions)
        assert result.host_decisions[-1].feedback_disposition == "source_ended"
        assert any(d.feedback_disposition == "accepted" for d in result.host_decisions)
        assert [f.visit for f in clients[0].feedback] == list(range(receipt.complete_visit_count))
        assert clients[0].owner != consumer_thread
        assert engines[0].closed
        assert len(set(engines[0].threads)) == 1
        assert engines[0].threads[0] not in (consumer_thread, clients[0].owner)
    finally:
        radio.close()
    assert clients[0].closed


@pytest.mark.parametrize("rate", [15_000_000, 20_000_000])
def test_wide_rate_uses_one_long_direct_async_request(rate):
    receipt = multirate_host_receipt(rate=rate, count=3)
    radio, clients, _ = setup(receipt, pacing=0)
    radio.open()
    try:
        session = radio.begin_session(receipt.plan, session_id=receipt.session_id)
        assert tuple(drain(session)) == receipt.visits
        result = session.finish()
        assert result.plan.geometry.sample_rate_hz == rate
        assert clients[0].direct_async_frames == 8192
    finally:
        radio.close()


def test_first_visit_replaces_buffer_open_clock_bracket():
    receipt = host_receipt(count=3)
    broad = SimpleNamespace(
        before_realtime_ns=1_000_000_000,
        before_monotonic_ns=2_000_000_000,
        after_realtime_ns=1_207_000_000,
        after_monotonic_ns=2_207_000_000,
    )
    precise = SimpleNamespace(
        before_realtime_ns=1_100_000_000,
        before_monotonic_ns=2_100_000_000,
        after_realtime_ns=1_101_500_000,
        after_monotonic_ns=2_101_500_000,
    )
    radio, clients, _ = setup(receipt, pacing=0, clock_brackets=(broad, precise))
    radio.open()
    try:
        session = radio.begin_session(receipt.plan, session_id=receipt.session_id)
        assert tuple(drain(session)) == receipt.visits
        session.finish()
        assert (
            session.start_clock_bracket.after_monotonic_ns
            - session.start_clock_bracket.before_monotonic_ns
            == 1_500_000
        )
    finally:
        radio.close()
    assert clients[0].calls.count("clock") >= 2


@pytest.mark.parametrize("fault", ["overflow", "detector_failure", "feedback_rejected"])
def test_decision_fault_preserves_every_native_visit_with_explicit_evidence(fault):
    receipt = host_receipt(count=13)
    radio, clients, engines = setup(
        receipt,
        pacing=0 if fault == "overflow" else 0.04,
        engine_delay=0.2 if fault == "overflow" else 0,
        engine_fail=fault == "detector_failure",
        reject=fault == "feedback_rejected",
        read_ahead=64,
    )
    radio.open()
    try:
        session = radio.begin_session(receipt.plan, session_id=receipt.session_id)
        assert tuple(drain(session)) == receipt.visits
        result = session.finish()
        assert result.valid_sample_count == receipt.valid_sample_count
        assert len(result.host_decisions) == receipt.complete_visit_count
        if fault == "overflow":
            degraded = [d for d in result.host_decisions if d.health == "queue_overflow"]
            assert degraded and all(
                d.numerics is None and d.feedback_outcome == "unknown" for d in degraded
            )
            assert [f.visit for f in clients[0].feedback] == list(
                range(receipt.complete_visit_count)
            )
        elif fault == "detector_failure":
            assert all(
                d.health == "detector_failure" and d.feedback_outcome == "unknown"
                for d in result.host_decisions
            )
        else:
            assert result.host_decisions[0].feedback_disposition == "rejected"
            assert all(
                d.feedback_disposition == "not_submitted"
                and d.feedback_error
                and d.feedback_call_elapsed_ns is None
                for d in result.host_decisions[1:]
            )
            assert clients[0].calls.count("feedback") == 1
    finally:
        radio.close()
    assert engines[0].closed


def test_cancel_is_only_a_cross_thread_signal_and_restoration_stays_owned():
    receipt = host_receipt(count=5)
    radio, clients, _ = setup(receipt)
    radio.open()
    try:
        session = radio.begin_session(receipt.plan, session_id=receipt.session_id)
        first = session.read_visit()
        session.request_cancel()
        remaining = drain(session)
        assert (first.evidence, *remaining) == receipt.visits
        assert session.finish().terminal.state == "cancelled"
    finally:
        radio.close()
    assert clients[0].closed and "terminal" in clients[0].calls


def test_exhausted_native_read_ahead_fails_capture_and_closes_on_its_owner():
    receipt = host_receipt(count=6)
    radio, clients, _ = setup(receipt, pacing=0, read_ahead=1)
    radio.open()
    session = radio.begin_session(receipt.plan, session_id=receipt.session_id)
    deadline = time.monotonic() + 3
    while not session.stopped and time.monotonic() < deadline:
        time.sleep(0.01)
    assert session.stopped
    with pytest.raises(RuntimeError, match="read-ahead exhausted"):
        drain(session)
    with pytest.raises(RuntimeError, match="read-ahead exhausted"):
        radio.close()
    assert clients[0].closed


def test_admission_failure_does_not_construct_a_worker_or_leave_a_thread():
    receipt = host_receipt(count=2)
    radio, _, engines = setup(receipt)

    def fail(*args):
        raise RuntimeError("synthetic admission rejection")

    radio._client_factory = fail
    radio.open()
    with pytest.raises(RuntimeError, match="admission rejection"):
        radio.begin_session(receipt.plan, session_id=receipt.session_id)
    with pytest.raises(RuntimeError, match="admission rejection"):
        radio.close()
    assert not engines
    assert radio.open() == radio.identity
    radio.close()


def test_slow_restoration_does_not_expire_pending_terminal_feedback():
    receipt = host_receipt(count=4)
    radio, clients, _ = setup(receipt, engine_delay=0.01)
    radio.open()
    try:
        session = radio.begin_session(receipt.plan, session_id=receipt.session_id)
        clients[0].restoration_delay = 1.1
        drain(session)
        recorded = session.finish()
        assert all(record.health == "healthy" for record in recorded.host_decisions)
        assert recorded.host_decisions[-1].feedback_disposition == "source_ended"
    finally:
        radio.close()
