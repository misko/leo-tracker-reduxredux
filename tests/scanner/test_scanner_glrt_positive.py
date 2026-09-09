"""Positive-only SDK and independent feedback, using the actual native worker."""

import ctypes as ct
import errno
import time

import numpy as np
import pytest

from tests.scanner.test_adaptive_scan import Observation
from tests.scanner.test_scanner_glrt_port import Config, Session
from tests.scanner.test_scanner_glrt_port import artifacts as artifacts
from tests.scanner.test_scanner_glrt_port import port as port
from tools.qualify_presence_dwell_controls import generate


class PositivePolicy(ct.Structure):
    _fields_ = [("minimum_exact_score", ct.c_double), ("minimum_margin", ct.c_double)]


@pytest.fixture(scope="module")
def positive_port(port):
    port.leo_scanner_glrt_open_positive.argtypes = [
        ct.POINTER(ct.c_void_p),
        ct.POINTER(Config),
        ct.c_char_p,
        ct.c_char_p,
        ct.POINTER(PositivePolicy),
    ]
    port.leo_scanner_glrt_observation.argtypes = [ct.c_void_p, ct.POINTER(Observation)]
    return port


def feedback(s):
    out = Observation()
    until = time.monotonic() + 5
    while time.monotonic() < until:
        ret = s.port.leo_scanner_glrt_observation(s.ptr, ct.byref(out))
        if ret:
            assert ret == 1
            return out
        time.sleep(0.005)
    pytest.fail("bounded feedback wait expired")


def supply_pilot(s, edge):
    start = 2**53 + 347
    selected, _ = generate(s.rate, edge, 91, "pilot", 4)
    iq = np.empty((len(selected), 4), dtype=np.int16)
    iq[:, :2], iq[:, 2:] = 30000, selected
    before = iq.copy()
    assert s.visit(0, start, 4, int(edge == "upper")) == 0
    n = s.rate // 50 - 17
    for offset in range(0, len(iq), n):
        assert s.block(start + offset, iq[offset : offset + n]) == 0
    assert s.port.leo_scanner_glrt_finish(s.ptr, 0) == 0
    np.testing.assert_array_equal(iq, before)
    return start, start + len(iq)


@pytest.mark.parametrize("rate", [2500000, 5000000])
@pytest.mark.parametrize("edge", ["lower", "upper"])
@pytest.mark.parametrize("wire_first", [False, True])
def test_positive_result_and_feedback_are_independent(
    positive_port, artifacts, tmp_path, rate, edge, wire_first
):
    s = Session(
        positive_port, artifacts[0], tmp_path, rate, positive_policy=PositivePolicy(0.175, 0.025)
    )
    try:
        start, end = supply_pilot(s, edge)
        if wire_first:
            records = [r for f in s.drain() for r in f.results]
            o = feedback(s)
        else:
            o = feedback(s)
            records = [r for f in s.drain() for r in f.results]
        assert len(records) == 1
        r = records[0]
        assert r.verdict == "starlink" and r.reason == "complete"
        assert r.exact_score >= 0.175 and r.margin >= 0.025
        assert (o.outcome, o.healthy, o.target) == (1, 1, 3 if edge == "lower" else 7)
        assert (o.session, o.generation, o.visit, o.valid_start, o.valid_end) == (
            71,
            9,
            0,
            start,
            end,
        )
        assert (o.rate_hz, o.rx) == (rate, 1)
        assert s.port.leo_scanner_glrt_observation(s.ptr, ct.byref(Observation())) == -errno.ENODATA
    finally:
        s.close()


def test_completed_below_threshold_search_is_not_a_public_absence_claim(
    positive_port, artifacts, tmp_path
):
    s = Session(
        positive_port, artifacts[0], tmp_path, 2500000, positive_policy=PositivePolicy(10, 0.025)
    )
    try:
        supply_pilot(s, "lower")
        o = feedback(s)
        assert (o.outcome, o.healthy) == (2, 1)
        r = [r for f in s.drain() for r in f.results][0]
        assert r.verdict == "unavailable" and r.reason == "incomplete_search"
        assert r.confirmation_end > r.confirmation_start
    finally:
        s.close()


def test_cancelled_input_yields_unknown_without_consuming_wire_record(
    positive_port, artifacts, tmp_path
):
    s = Session(
        positive_port, artifacts[0], tmp_path, 5000000, positive_policy=PositivePolicy(0.175, 0.025)
    )
    try:
        assert s.visit(0, 100) == 0
        assert s.port.leo_scanner_glrt_finish(s.ptr, 1) == 0
        o = feedback(s)
        assert (o.outcome, o.healthy, o.valid_start) == (0, 0, 100)
        records = [r for f in s.drain() for r in f.results]
        assert len(records) == 1 and records[0].reason == "cancelled"
    finally:
        s.close()


def test_old_entrypoint_still_disallows_scheduling_feedback(positive_port, artifacts, tmp_path):
    s = Session(positive_port, artifacts[0], tmp_path, 2500000)
    try:
        assert s.port.leo_scanner_glrt_observation(s.ptr, ct.byref(Observation())) == -errno.ENOTSUP
    finally:
        s.close()


@pytest.mark.parametrize(
    "values", [None, (-1, 0.025), (float("nan"), 0.025), (0.175, 0), (0.175, float("inf"))]
)
def test_bad_policy_fails_before_starting_worker(positive_port, values):
    p = PositivePolicy(*values) if values else None
    output = ct.c_void_p(123)
    assert (
        positive_port.leo_scanner_glrt_open_positive(
            ct.byref(output),
            ct.byref(Config()),
            b"/not-accessed",
            b"/not-accessed",
            ct.byref(p) if p else None,
        )
        == -errno.EINVAL
    )
    assert output.value == 123
