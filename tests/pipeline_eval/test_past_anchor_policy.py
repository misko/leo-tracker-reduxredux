from copy import deepcopy
from fractions import Fraction

from reports.ALGO08.v3 import past_anchor_policy as policy


def block(anchor_rate, margins):
    observed = policy.ObservedBlock()
    for i in range(4):
        observed.observe("anchor", "lane", 1. if i < anchor_rate else None)
    for margin in margins:
        observed.observe("short", "lane", margin)
    return observed


def test_persistent_conservative_rate_cap_uses_inclusive_historical_rank():
    previous = [block(1, [0.9, 0.8, 0.7, 0.6]), block(2, [0.5, 0.4, 0.3, 0.2])]
    eligible, keep, cutoff = policy.threshold(previous)
    assert eligible and keep == Fraction(1, 2)
    assert cutoff == {"lane": 0.6}
    previous[1] = block(2, [0.5, 0.4, None, None])
    assert policy.threshold(previous) == (True, None, {})
    assert policy.threshold([None, previous[1]]) == (False, None, {})


def test_new_block_decisions_use_only_previous_completed_visit_blocks():
    probes = [dict(visit_index=visit, receiver_id=radio, channel=1, edge="lower", actual_rf_hz=10.7e9,
                   valid_start_counter=visit*1000,
                   candidates=[dict(passed_fractional_margin_gate=True, fractional_margin=0.2 + (visit % 8)/10)]
                   if visit % 8 or visit % 16 == 0 else [])
              for visit in range(384) for radio in (0, 1)]
    doc = dict(source=dict(probes=probes, session_id="testing", sample_rate_hz=10_000_000),
               provenance=dict(window_count=384, processed_windows=384, invalid_capture=0))
    baseline = policy.apply(doc, None)
    assert baseline["first"]["eligible"]["visit"] == 257
    assert baseline["first"]["removed"]["visit"] == 257
    assert all(row["kept"] for row in baseline["decisions"] if row["mode"] == "anchor" or row["visit"] < 256)
    future = deepcopy(doc)
    for row in future["source"]["probes"][2*370:]:
        for factor in row["candidates"]:
            factor["fractional_margin"] = 1.0
    next_run = policy.apply(future, None)
    earlier = lambda result: [row for row in result["decisions"] if row["visit"] < 370]
    assert earlier(next_run) == earlier(baseline)
