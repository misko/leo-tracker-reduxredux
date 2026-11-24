from itertools import product

import pytest

from reports.ALGO08.v3.interleaved_receiver_budget import budget, omitted_lanes, price


def test_counts_bound_every_possible_truncated_cycle_without_reading_detections():
    for cycles in range(4):
        outcomes = {}
        for counts in product(range(8), repeat=cycles):
            outcomes.setdefault(sum(counts), set()).add(2 * sum((n+1)//2 for n in counts))
        for shorts, costs in outcomes.items():
            assert omitted_lanes(2*cycles,2*shorts) == (min(costs),max(costs))
    with pytest.raises(ValueError, match="stereo lane counts"):
        omitted_lanes(2,16)


def test_allowance_charges_extra_work_once_and_respects_both_gates():
    row = dict(installed_s=100, candidate_s=58, solver_s=15, short_s=14, full_lanes=2, short_lanes=14)
    for side in ("favorable", "conservative"):
        assert budget([row],1.,side)["maximum_us_per_omitted_lane"] == pytest.approx(0., abs=1e-8)
        assert budget([row],1.5,side)["maximum_us_per_omitted_lane"] == pytest.approx(625000)
    slow = dict(row, installed_s=10, candidate_s=8., solver_s=0., short_s=2.)
    assert budget([row, slow, slow], 1.5, "favorable")["maximum_us_per_omitted_lane"] is None


def test_conservative_order_reverses_when_replacement_is_more_expensive_than_original():
    row = dict(installed_s=100, candidate_s=58, solver_s=0, full_lanes=4, short_lanes=12, short_s=1)
    for cost in (0, 100000):
        fast = price([row],1,cost,"favorable")
        slow = price([row],1,cost,"conservative")
        assert fast["summed_speedup"] > slow["summed_speedup"]
