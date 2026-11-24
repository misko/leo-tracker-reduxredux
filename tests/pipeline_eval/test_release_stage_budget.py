import json
from pathlib import Path
from statistics import median

import pytest

from reports.ALGO08.v3.release_stage_budget import gates, required_pre_speedup, summarize


def test_unpartitioned_time_stays_in_denominator_and_bounds_both_gates():
    rows = [dict(elapsed_s=10, pre_s=7, post_s=3), dict(elapsed_s=2, pre_s=None, post_s=None)]
    fast = gates(rows, .25, 1, optimistic=True)
    slow = gates(rows, .25, 1, optimistic=False)
    assert fast == pytest.approx(dict(median_ratio=median([.475, .25]), sum_ratio=5.25/12))
    assert slow == pytest.approx(dict(median_ratio=median([.475, 1]), sum_ratio=6.75/12))
    assert gates(rows, .5, .5, optimistic=False) == gates(rows, .5, .5, optimistic=True)


def test_gate_search_accounts_for_the_changing_median():
    rows = [dict(elapsed_s=9, pre_s=7, post_s=2), dict(elapsed_s=1, pre_s=.3, post_s=.7)]
    for optimistic in (True, False):
        required = required_pre_speedup(rows, .7, optimistic)
        assert max(gates(rows, 1/required, .7, optimistic=optimistic).values()) == pytest.approx(.5)
        assert max(gates(rows, 1/(required-.01), .7, optimistic=optimistic).values()) > .5
    assert required_pre_speedup([dict(elapsed_s=1, pre_s=.1, post_s=.9)], 1, False) is None


def test_published_measurements_reproduce_both_gates_and_all_archived_cases():
    path = Path(__file__).resolve().parents[2] / "reports/ALGO08/v3/measurements/release-stage-budget.json"
    data = json.loads(path.read_bytes())
    rows = data["rows"]
    assert len({r["case"] for r in rows}) == len(rows) == 100
    assert sum(r["pre_s"] is None for r in rows) == 5
    summary = summarize(rows)
    assert summary == data["summary"]
    assert summary["groups"]["all_partitioned"]["summed_pre_fraction"] == pytest.approx(.678885899)
    assert summary["gates"]["optimistic_unpartitioned"]["required_pre_speedup"]["1.5"] == pytest.approx(2.34816027)
