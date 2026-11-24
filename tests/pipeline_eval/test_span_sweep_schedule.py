import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
from span_sweep_schedule import audit, plan, price, replay, span_order


def timeline(sweeps, omitted=(), spacing=4_000_000):
    return [
        (visit, visit % 8 + 1, visit % 8 + 10_000_000_000, sample, mode)
        for visit in range(sweeps * 8)
        if visit not in omitted
        for sample in [visit // 8 * spacing + visit % 8]
        for mode in ["full" if visit // 8 % 8 == 0 else "short_primary"]
    ]


def test_nested_span_order_resolves_gaps_deterministically():
    assert span_order(0) == []
    assert span_order(1) == [0]
    assert span_order(9) == [0, 8, 4, 2, 6, 1, 3, 5, 7]
    result = plan(timeline(81, omitted={4}), 81 * 8)
    early, later = [result["stages"][f"span_{name}"] for name in ("third", "half")]
    assert set(early["core"]) <= set(later["core"])
    assert set(early["paid"]) <= set(later["paid"])
    assert set(range(640, 648)).issubset(early["core"])
    assert 4 not in early["paid"]
    assert len(result["stages"]["span_full"]["paid"]) == 647


def test_history_closure_includes_empty_admitted_slots_but_no_skipped_hypotheses():
    rows = timeline(10, omitted={36})
    result = plan(rows, 80, width=8)
    stage = result["stages"]["anchors"]
    assert stage["paid"] == [i for i in range(72) if i != 36]
    probes = [
        dict(visit_index=visit, channel=channel, actual_rf_hz=rf, valid_start_counter=sample,
             receiver_id=radio,
             candidates=[] if visit == 15 else [dict(fractional_tracking_cfo_hz=-2000 + sample / 1e7,
                                                     fractional_margin=0.03, candidate_rank=0)])
        for visit, channel, rf, sample, _ in rows for radio in (0, 1)
    ]
    full = replay(probes, {row[0] for row in rows})
    same = audit(probes, full, stage, {"c0": {(64, 0)}}, context=True)
    changed = audit(probes, full, stage, {"c0": {(64, 0)}}, context=False)
    assert same["per_radio"]["0"]["protected_history_vote_diffs"] == 0
    assert same["per_arm"]["c0"]["paid_history"] == 1
    assert changed["per_arm"]["c0"]["paid_history"] == 0


def test_long_gap_excludes_context_and_nonphysical_sweeps_are_rejected():
    result = plan(timeline(9, spacing=80_000_001), 72, width=8)
    assert result["stages"]["anchors"]["paid"] == result["anchors"]
    rows = timeline(9)
    rows[0] = (0, 2, *rows[0][2:])
    with pytest.raises(ValueError, match="eight-channel sweep"):
        plan(rows, 72, width=8)


def test_only_disjoint_short_stage_earns_estimated_credit():
    cost = dict(acquire=dict(cpu_ns=15_000_000_000, wall_ns=20_000_000_000),
                native=dict(native_calls={"full": 4, "short_primary": 12},
                            native_cpu_ns={"full": 2_000_000_000, "short_primary": 6_000_000_000}))
    accounting = price(cost, 2, 4, 8)
    assert accounting["skipped_short_lanes"] == 8
    assert accounting["gross_mean_short_credit_cpu_s"] == 4
    assert accounting["original_other_acquisition_cpu_s"] == 7
    assert accounting["fallback_retained_short_prefix_bytes"] == 3_840_000
