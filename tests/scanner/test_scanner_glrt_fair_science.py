"""Fair-admission data fidelity and pressure recovery; synthetic IQ, no RF."""

import ctypes as ct
import os
import signal

import numpy as np
import pytest

from tests.scanner.test_scanner_glrt_fair_admission import admission_stats, feed, finish
from tests.scanner.test_scanner_glrt_fair_admission import fair as fair
from tests.scanner.test_scanner_glrt_port import artifacts as artifacts
from tests.scanner.test_scanner_glrt_positive import feedback, supply_pilot
from tests.scanner.test_scanner_glrt_protection import pressure, stats
from tests.scanner.test_scanner_glrt_protection import protected_port as protected_port
from tools.presence_dwell import NativeDwell
from tools.qualify_presence_dwell_controls import generate


@pytest.mark.parametrize("edge", ["lower", "upper"])
def test_fair_worker_matches_fractional_direct_oracle(fair, artifacts, edge):
    s = fair
    iq, _ = generate(s.rate, edge, 91, "pilot", 4)
    with NativeDwell(artifacts[1], s.rate, edge, 4096) as oracle:
        expected = oracle.run(iq, maximum=1, seeded=False)
    assert expected.confirmations[0].candidate_count == 1
    candidate = expected.confirmations[0].candidates[0]
    assert candidate.fractional_complete
    start, end = supply_pilot(s, edge)
    rows = [r for frame in s.drain() for r in frame.results]
    assert len(rows) == 1
    row = rows[0]
    observation = feedback(s)
    assert (row.valid_start, row.valid_end) == (start, end)
    assert row.verdict == "starlink" and observation.outcome == observation.healthy == 1
    assert row.epoch_sample_counter == row.confirmation_start + candidate.epoch > 2**53
    for field, value in (
        ("fractional_offset_samples", candidate.fractional_offset_samples),
        ("cfo_hz", candidate.tracking_cfo_hz),
        ("exact_score", candidate.exact_score),
        ("control_score", candidate.control_score),
        ("margin", candidate.margin),
    ):
        assert getattr(row, field) == pytest.approx(value, rel=1e-9, abs=1e-10)


def test_pressure_aborts_third_partial_slot_and_recovers_without_fifo_hole(fair):
    s = fair
    count = s.rate // 50
    start = 2**53 + 347 + s.rate * 240 // 1000
    iq = np.zeros((count, 4), dtype=np.int16)
    iq[:, :2] = 30000
    os.kill(s.worker_pid, signal.SIGSTOP)
    try:
        feed(s, 0, 0)
        feed(s, 1, 1)
        assert s.visit(2, start, 3, 0) == 0
        assert s.block(start, iq) == 0
        assert stats(s).occupied_slots == 3
        pressure(s, 1)
        for window in range(1, 6):
            assert s.block(start + window * count, iq) == 0
        assert stats(s).occupied_slots == 1 and admission_stats(s).pending == 0
    finally:
        os.kill(s.worker_pid, signal.SIGCONT)
    for visit in range(3):
        observation = feedback(s)
        assert observation.visit == visit and observation.healthy == 1
        if visit:
            assert observation.outcome == 0
    for _ in range(4):
        pressure(s, 0)
    feed(s, 3, 3)
    assert feedback(s).visit == 3
    rows = finish(s)
    assert [r.visit for r in rows] == [0, 1, 2, 3]
    assert [r.search_window_mask for r in rows] == [63, 0, 0, 63]
    assert not stats(s).disabled and stats(s).resumptions == 1
    assert np.all(iq[:, :2] == 30000) and not np.any(iq[:, 2:])
    value = ct.c_uint32()
    assert s.port.leo_scanner_glrt_skip_cause(s.ptr, 2, ct.byref(value)) == 0
    assert value.value == 1
