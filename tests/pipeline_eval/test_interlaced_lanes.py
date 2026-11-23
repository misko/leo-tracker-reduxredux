from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
from interlaced_lanes import choose, slots
from sparse_consensus import paid_visits


def stream(n):
    return [dict(channel=i % 3, actual_rf_hz=i % 3, edge="upper", visit_index=i, valid_start_counter=i*10,
                 receiver_id=rx, candidates=[]) for i in range(n) for rx in (0, 1)]


@pytest.mark.parametrize("size", range(1, 22))
def test_exact_cost_and_complement_at_every_truncation(size):
    rows = stream(size)
    normal, reverse = (slots(rows, swap) for swap in (False, True))
    assert {index ^ 1 for index in normal} == reverse
    nominal = {i for i, row in enumerate(rows) if row["visit_index"] in paid_visits(rows)}
    for ch in range(3):
        for rx in (0, 1):
            lane = {i for i, row in enumerate(rows) if row["channel"] == ch and row["receiver_id"] == rx}
            assert len(normal & lane) == len(nominal & lane)


def test_only_paid_peaks_and_clocks_enter_selection():
    rows = stream(12)
    paid = slots(rows, False)
    peak = dict(fractional_margin=.5, passed_fractional_margin_gate=True, candidate_rank=0)
    for i, row in enumerate(rows):
        row["candidates"] = [peak] if i in paid else [None]
    picks, stats = choose(rows, [1e9]*len(rows), swap=False)
    assert {i for i, v in enumerate(picks) if v} == paid
    assert stats["paid_native_cpu_s"] == len(paid)
