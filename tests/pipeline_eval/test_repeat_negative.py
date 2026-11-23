from math import nan

import numpy as np
import pytest

from reports.ALGO08.v3.repeat_negative import REPEATS, Screen, compile_kernel, detector_row, keep, summarize


@pytest.fixture(scope="module")
def screen(tmp_path_factory):
    binary = tmp_path_factory.mktemp("repeat-pilot") / "gate.so"
    compile_kernel(binary)
    return Screen(binary)


def test_exact_repeat_of_one_radio_and_no_repeat_evidence_for_constant_or_tone(screen):
    rng = np.random.default_rng(5)
    data = np.empty((200_000, 2, 2), dtype="<i2")
    wave = rng.integers(-32768, 32768, size=(40_000, 2), dtype=np.int16)
    data[:, 0] = np.tile(wave, (5, 1))
    data[:, 1] = 32_000
    assert screen.score(data, 0, "short_primary") > .98
    assert screen.score(data, 1, "short_primary") == 0
    phase = np.arange(200_000) * 2*np.pi/71
    data[:, 1, 0], data[:, 1, 1] = np.rint(30000*np.cos(phase)), np.rint(30000*np.sin(phase))
    assert screen.score(data, 1, "full") < 1e-7
    assert screen.score(data, 0, "full") > .98


def test_short_gate_reads_only_its_prefix(screen):
    rng = np.random.default_rng(7)
    data = np.zeros((200_000, 2, 2), dtype="<i2")
    data[120_000:, 0] = np.tile(rng.integers(-1200, 1200, size=(40_000, 2), dtype=np.int16), (2, 1))
    assert screen.score(data, 0, "short_primary") == 0
    assert screen.score(data, 0, "full") > .98
    assert np.isnan(screen.score(data[1:], 0, "full"))


def test_anchors_and_invalid_scores_reach_original_but_low_nonanchor_skips(screen):
    calls = []
    signed = ((1, 99, -.25, -29_210., .22, .13), (0, 103, .45, 63_430., .24, .11))

    class Original:
        def run(self, _samples, lane, center):
            calls.append((lane, center))
            return signed, [6, 8]

    native = Original()
    data = np.zeros((200_000, 2, 2), dtype="<i2")
    assert keep(False, .10, .10) and keep(False, nan, .10)
    always, anchored = detector_row(native, screen, data, 0, -42, "full", True, .10, True)
    empty, skipped = detector_row(native, screen, data, 1, 43, "full", False, .10, True)
    fallback, invalid = detector_row(native, screen, data[1:], 1, 43, "full", False, .10, True)
    assert always == fallback == signed and empty == () and calls == [(0, -42), (1, 43)]
    assert anchored["gate"] == [0, 0] and invalid["score"] is None and skipped["skipped"]


def test_summary_keeps_secondary_and_wasted_gate_cost_visible():
    paid = dict(total=[200, 201], native=[190, 192], gate=[0, 0])
    gated = dict(total=[17, 18], native=[0, 0], gate=[16, 17])
    rows = [dict(anchor=False, score=score, signed=factors, selected=(), skipped=True,
                 repeats=[dict(direct=paid, gate=gated)] * REPEATS)
            for score, factors in ((.04, [(1,), (0,)]), (.02, []))]
    result = summarize(rows)
    assert result["missed_by_rank"] == {1: 1, 0: 1}
    assert result["full_recall_hindsight"] == dict(cutoff=.04, empty_skips=1, native_ns=[190, 192])
    assert result["gate_ns"] == [32, 34]
