from copy import deepcopy

import adaptive_anchor_placement as policy
import pytest


def factor(hz):
    return dict(integer_epoch_sample=1000, fractional_epoch_offset_samples=.1,
                fractional_tracking_cfo_hz=hz)


def visit(slot, short, long, *, stream=("lower", 1, 11.4e9), missing=False):
    counter = 100_000_000+slot*1_000_000
    rows = [dict(visit_index=slot, receiver_id=i, channel=stream[1], actual_rf_hz=stream[2],
                 valid_start_counter=counter, candidates=[]) for i in (0,1)]
    choices = {policy.FULL: [long,long]}
    if not missing:
        choices[policy.SHORT] = [short,short]
    return dict(stream=stream, slot=slot, counter=counter, probes=rows,
                choices=choices, cpu={policy.FULL: 30,policy.SHORT: 10})


def test_adaptive_uses_only_previous_paid_short_stereo_empties():
    rows = [visit(i, None if i < 2 else factor(1000), factor(1500)) for i in range(8)]
    schedule = policy.freeze_schedule(rows, "lagged_empty")
    full, = [item for item in schedule if item["aperture"] == policy.FULL]
    assert full["phase"] == 2 and full["trigger"] == "past_two_empty"
    assert full["prior_empty_counters"] == [rows[0]["counter"],rows[1]["counter"]]

    changed = deepcopy(rows)
    changed[2]["choices"][policy.SHORT] = [None,None]
    changed[3]["choices"][policy.FULL] = [None,None]
    assert policy.freeze_schedule(changed, "lagged_empty")[:3] == schedule[:3]


def test_missing_opportunity_clears_predecessors_and_never_becomes_a_factor():
    rows = [visit(i, None if i < 3 else factor(1000), factor(1500), missing=i==1)
            for i in range(9)]
    schedule = policy.freeze_schedule(rows,"lagged_empty")
    assert len(schedule) == 8
    assert 1 not in [row["index"] for row in schedule]
    full, = [item for item in schedule if item["aperture"] == policy.FULL]
    assert full["index"] == 8 and full["trigger"] == "force_last"
    out = policy.unknown_predecessors(rows)
    assert out["unmeasured_short_lanes"] == 2
    assert out["later_lanes_with_missing_short_alternative_in_original_history_window"] == 14


def test_one_paired_callback_per_antenna_and_hindsight_uses_net_difference():
    original, wrong = factor(1000), factor(3000)
    rows = [visit(i, original, wrong if i == 0 else original) for i in range(8)]
    rows[5]["choices"][policy.SHORT] = [None,None]
    named = [dict(p, candidates=[original]) for row in rows for p in row["probes"]]
    owned = [[policy.observation(p,"signed"), 1, "role"] for p in named]
    scope = dict(named=named, baseline=named, session="signed",
                 owned={arm:owned for arm in policy.ARMS},
                 successor={arm:owned for arm in policy.ARMS})
    schedules = {p:policy.freeze_schedule(rows,p) for p in policy.POLICIES}
    scored = policy.scope_scores(rows, schedules, scope)
    assert scored["oracle"]["all"] == dict(
        all_short_matches=14, best_same_budget_matches=16, gain_above_all_short=2,
    )
    assert scored["policies"]["periodic"]["complete"]["stats"]["all"]["matched"] == 12
    late = scored["policies"]["fixed_late"]["complete"]["stats"]["all"]
    assert late["matched"] == 14
    assert late["gained_over_periodic"] == 2 and late["lost_from_periodic"] == 0
    assert scored["policies"]["periodic"]["complete"]["clocks"] == dict(
        native_cpu_ns=100, short_first_extra_cpu_ns=10,
    )


def test_large_counter_gap_prevents_two_empty_trigger():
    rows = [visit(i, None if i < 2 else factor(1000), factor(1500)) for i in range(8)]
    for row in rows[2:]:
        row["counter"] += policy.MAX_GAP+1
    schedule = policy.freeze_schedule(rows, "lagged_empty")
    assert [x["phase"] for x in schedule if x["aperture"]==policy.FULL] == [7]


def test_full_replay_refuses_to_fill_unmeasured_predecessors():
    rows = [visit(0,None,factor(1000),missing=True)]
    schedule = policy.freeze_schedule(rows,"periodic")
    with pytest.raises(ValueError,match="Unknown selected predecessors"):
        policy.causal_readout(rows, schedule, None, None)
