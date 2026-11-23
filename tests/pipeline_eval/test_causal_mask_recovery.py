from pathlib import Path
import sys

import pytest

HERE = Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"
sys.path.insert(0, str(HERE))

from causal_mask_recovery import Recovery, compare, replay, supported, uniform


def test_quota_accumulates_on_own_stream_and_bought_lane_does_not_feed_history():
    lane = (0, "upper", 1, 11_000_000_000)
    peer = (1, *lane[1:])
    policy = Recovery("recent", (1, 4))
    for counter in range(1, 4):
        assert not policy.buy(lane, counter)
    policy.observe_base(peer, 3, 40_000)
    assert not policy.buy(lane, 4)
    policy.observe_base(lane, 5, 40_000)
    assert policy.buy(lane, 6)
    assert list(policy.history[lane]) == [(5, 40000)]
    assert not policy.buy(lane, 7)
    policy.observe_base(lane, 8, None)
    for counter in range(9, 15):
        assert not policy.buy(lane, counter)


def test_signed_slope_and_physical_horizon_use_only_distinct_prior_positive_cfo():
    trace = [(0, -120_000), (10_000_000, -112_000)]
    assert supported(trace, 80_000_000, "smooth")
    assert not supported(trace, 80_000_001, "smooth")
    assert supported(trace, 80_000_001, "recent")
    assert not supported([(0, -120_001), trace[-1]], 20_000_000, "smooth")
    assert not supported([(0, None), trace[-1]], 20_000_000, "smooth")
    assert not supported(trace, 10_000_000, "smooth")


def test_replay_rejects_a_current_unpaid_factor():
    rows = [dict(visit_index=i, receiver_id=r, edge="upper", channel=1, actual_rf_hz=11_000_000_000,
                 valid_start_counter=i*10_000_000, candidates=[]) for i in range(4) for r in range(2)]
    rows[5]["candidates"] = [dict(passed_fractional_margin_gate=True, fractional_tracking_cfo_hz=300)]
    with pytest.raises(ValueError, match="censored target-mask"):
        replay(dict(source=dict(probes=rows)), "recent", (1, 4))


def test_matched_baselines_charge_empty_calls_and_excluded_owner_labels_separately():
    slots = [(i, 0) for i in range(12)]
    assert uniform(slots, 3) == [slots[i] for i in (2, 6, 10)]
    assert uniform(slots, 0) == []
    plan = dict(rule="recent", fraction=[1, 4], policy_cpu_s=0.001,
                lanes=[dict(omitted=slots, bought=[slots[i] for i in (3, 6, 9)])])
    oracle = dict(c0={slots[3], slots[6]}, fitted_c={slots[0]})
    row = compare(plan, set(slots), {slots[i] for i in (0, 3, 6)}, oracle, 0.001)
    assert row["recovered_calls"] == 3
    assert row["empty_buys"] == 1
    assert row["owner"]["c0"] == dict(recalled=2, uniform=1, expected=0.5, positives_outside_owner=0, possible=2)
    assert row["owner"]["fitted_c"]["positives_outside_owner"] == 2
    assert row["remaining_after_policy_s"] == pytest.approx(0.008)
