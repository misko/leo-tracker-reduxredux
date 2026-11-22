import pytest

from tools.pipeline_eval.variants.experimental.residual_rescue import PrimaryRescue, primary_only


def factor(hz, rank=0):
    return dict(fractional_tracking_cfo_hz=hz, candidate_rank=rank, fractional_margin=.2)


def append(policy, trace, visit, full, *, lane=0, channel=3, counter=None, bad_primary=False):
    timestamp = visit * 4_000_000 if counter is None else counter
    metadata = dict(visit_index=visit, receiver_id=lane, channel=channel, actual_rf_hz=11e9,
                    valid_start_counter=timestamp)

    def measure(residual):
        trace.append((visit, lane, residual))
        if not residual and bad_primary:
            return [factor(12340)]
        return full if residual else primary_only(full)

    return policy.visit(metadata, measure)


def test_resolves_newest_first_and_reuses_historical_slot_without_changing_schedule():
    policy, trace = PrimaryRescue(), []
    h = 1200
    rows = [[factor(h)], [factor(50000), factor(h, 1)], [factor(h)], [factor(h)], [factor(h)]]
    selected = []
    for i, factors in enumerate(rows):
        _, _, admitted = append(policy, trace, i, factors)
        selected.append(admitted)
    assert trace == [(0, 0, True), (1, 0, False), (2, 0, False), (3, 0, True),
                     (2, 0, True), (1, 0, True), (4, 0, False)]
    assert selected == [[], [], [], [factor(h)], [factor(h)]]
    assert policy.foreground.reasons == {"sentinel": 2, "skip": 3}
    assert policy.counts["historical_residuals_found"] == 1
    assert policy.counts["primary_thresholds_restored"] == 1
    history = policy.foreground.continuation.by_lane[0, 3, 11e9]
    assert list(history)[1] == (4_000_000, (50000, h))
    assert len(history) == len(rows)


def test_residual_only_historical_factor_can_donate_and_other_lane_is_not_queried():
    policy, trace = PrimaryRescue(), []
    h = 1200
    target = [[factor(h)], [factor(h, 1)], [factor(h)], [factor(h)]]
    for i, factors in enumerate(target):
        _, _, chosen = append(policy, trace, i, factors)
        append(policy, trace, i, [], lane=1)
    assert chosen == [factor(h)]
    assert [entry for entry in trace if entry[1] == 1] == [
        (0, 1, True), (1, 1, False), (2, 1, False), (3, 1, True)
    ]
    assert policy.counts["historical_full_queries"] == 2
    assert policy.counts["peak_pending_lanes"] > policy.counts["peak_stereo_windows"]


def test_budget_eviction_releases_candidate_and_cannot_supply_late_vote():
    policy, trace = PrimaryRescue(max_pending=1), []
    h = 1200
    target = [[factor(h)], [factor(h, 1)], [factor(h)], [factor(h)]]
    for i, factors in enumerate(target):
        _, _, chosen = append(policy, trace, i, factors)
    assert chosen == []
    assert policy.counts["budget_evicted_pending"] == 1
    assert not policy.counts["historical_full_queries"]
    assert policy.counts["peak_pending_lanes"] == 1


def test_old_visits_end_at_the_time_horizon_and_twelve_slot_limit():
    policy, trace = PrimaryRescue(), []
    for i in range(16):
        append(policy, trace, i, [], counter=i * 1_000_000)
    assert policy.counts["history_evicted_pending"] == 2
    append(policy, trace, 16, [factor(1.0)], counter=100_000_000)
    assert policy.counts["expired_pending"] > 0
    assert not policy.counts["historical_full_queries"]


def test_backfill_rejects_changed_primary():
    policy, trace = PrimaryRescue(), []
    h = 1200
    append(policy, trace, 0, [factor(h)])
    append(policy, trace, 1, [factor(51000), factor(h, 1)], bad_primary=True)
    append(policy, trace, 2, [factor(h)])
    with pytest.raises(ValueError, match="changed the original primary"):
        append(policy, trace, 3, [factor(h)])
