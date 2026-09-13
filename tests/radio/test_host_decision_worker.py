"""Bounded computation, lossless input and explicit unknown/degraded results."""

import dataclasses as dc
import threading
import time

import numpy as np
import pytest
from pluto_plus.host_adaptive_hop import HostDecisionOutcome, HostFeedbackV1

from leo.analysis.host_decision import HostDecisionEvidence
from leo.radio.host_decision_worker import BoundedHostDecisionWorker


def source(visit=0):
    return HostFeedbackV1(
        17,
        9,
        13,
        visit,
        visit,
        visit * 1260000,
        visit * 1260000 + 1200000,
        1,
        7,
        HostDecisionOutcome.UNKNOWN,
        0,
        0,
        0,
        bytes(range(32)),
    )


def evidence():
    return HostDecisionEvidence(
        "detected",
        63,
        32,
        40,
        300000,
        True,
        100,
        True,
        0.1,
        10.0,
        0.25,
        0.04,
        2.0,
        17.0,
        18.0,
        (1.0,) * 6,
    )


class Engine:
    def __init__(self, gate=None, fail=False):
        self.gate, self.fail, self.calls, self.closed = gate, fail, [], False

    def run(self, iq, *, edge):
        self.calls.append((threading.get_ident(), int(iq[0, 0]), edge))
        if self.gate:
            assert self.gate.wait(2)
        if self.fail:
            raise ValueError("synthetic detector failure")
        assert iq.shape == (1200000, 2) and not iq.flags.writeable
        return evidence()

    def close(self):
        self.closed = True
        assert threading.get_ident() == self.calls[0][0]


def test_bound_includes_completed_results_and_source_input_is_owned():
    gate = threading.Event()
    engine = Engine(gate)
    worker = BoundedHostDecisionWorker(lambda: engine)
    iq = np.ones((1, 1200000), dtype=np.complex64)
    try:
        worker.submit(source(), iq, edge="upper")
        iq[:] = 2
        worker.submit(source(1), iq, edge="lower")
        iq[:] = 3
        with pytest.raises(RuntimeError, match="bounded capacity"):
            worker.submit(source(2), iq, edge="lower")
        assert worker.pending_count == worker.high_watermark == 2
    finally:
        gate.set()
        output = worker.finish()
    assert [r.source.visit for r in output] == [0, 1]
    assert [v[1] for v in engine.calls] == [1, 2]
    assert all(v[0] != threading.get_ident() for v in engine.calls)
    assert engine.closed and worker.finish() == ()
    with pytest.raises(RuntimeError, match="closed"):
        worker.submit(source(2), iq, edge="lower")


def test_complete_evidence_serializes_but_expired_result_stays_unknown():
    worker = BoundedHostDecisionWorker(Engine)
    worker.submit(source(), np.zeros((1, 1200000), dtype=np.complex64), edge="upper")
    (result,) = worker.finish()
    fresh = result.feedback(result.completed_ns)
    assert HostFeedbackV1.unpack(fresh.pack()) == fresh
    assert fresh.outcome == HostDecisionOutcome.DETECTED and fresh.screen_mask == 63
    assert result.feedback(result.submitted_ns + 1000000001) == source()
    assert result.evidence == evidence()


def test_detector_failure_is_explicit_unknown_without_healthy_negative():
    worker = BoundedHostDecisionWorker(lambda: Engine(fail=True))
    worker.submit(source(), np.zeros((1, 1200000), dtype=np.complex64), edge="upper")
    (result,) = worker.finish()
    assert result.feedback(time.monotonic_ns()) == source()
    assert result.evidence is None and "synthetic detector failure" in result.failure


@pytest.mark.parametrize("value", [float("nan"), float("inf"), 0.5, 32768, -32769])
def test_arbitrary_float_samples_cannot_be_rounded_into_detector_evidence(value):
    worker = BoundedHostDecisionWorker(Engine)
    iq = np.zeros((1, 1200000), dtype=np.complex64)
    iq[0, 100] = value
    with pytest.raises(ValueError, match="lossless CI16"):
        worker.submit(source(), iq, edge="lower")
    assert worker.pending_count == 0
    assert worker.finish() == ()


def test_already_evaluated_source_cannot_be_resubmitted_as_fresh_work():
    worker = BoundedHostDecisionWorker(Engine)
    with pytest.raises(ValueError, match="unevaluated"):
        worker.submit(
            dc.replace(source(), healthy=1, screen_mask=63),
            np.zeros((1, 1200000), dtype=np.complex64),
            edge="lower",
        )
    worker.finish()


def test_finish_timeout_still_closes_workspace_after_the_accepted_job_returns():
    gate = threading.Event()
    engine = Engine(gate)
    worker = BoundedHostDecisionWorker(lambda: engine)
    worker.submit(source(), np.zeros((1, 1200000), dtype=np.complex64), edge="lower")
    try:
        with pytest.raises(TimeoutError):
            worker.finish(timeout=0.001)
    finally:
        gate.set()
    deadline = time.monotonic() + 1
    while not engine.closed and time.monotonic() < deadline:
        time.sleep(0.001)
    assert engine.closed
