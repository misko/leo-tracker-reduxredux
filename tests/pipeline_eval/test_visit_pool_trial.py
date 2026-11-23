import numpy as np
import pytest

from reports.ALGO08.v3.visit_pool_trial import ARMS, CFO_HZ, PriorBank, aligned, matched, shortlist, summary


def score(center):
    return np.exp(-.5*((CFO_HZ-center)/1100.)**2)


def test_signed_drift_alignment_and_no_future_history():
    recent = 20_000_000
    final = 180_400.
    rate = -8000.
    histories = [(recent - int(1e7*t), 0., score(final - rate*t)) for t in (.9, .6, .3)]
    corrected = shortlist(aligned(recent, 0., histories, (rate,)), 0.)
    carried = shortlist(aligned(recent, 0., histories[-1:]), 0.)
    assert abs(corrected[0] - final) < 500.
    assert abs(carried[0] - final) > 1500.
    assert all(abs(a-b) >= 10000. for i, a in enumerate(corrected) for b in corrected[:i])
    with pytest.raises(ValueError, match="causal"):
        aligned(recent, 0., [(recent, 0., score(final))])


def test_same_lane_and_null_share_history_budget_but_different_rf():
    book = PriorBank()
    same = (0, 2, "lower", 1, 10_700_000_000.)
    null = (0, 2, "lower", 2, 10_900_000_000.)
    alternate_lane = (1, *null[1:])
    for i in range(1, 5):
        book.push(same, i * 1_000_000, 0., score(50_000.))
        if i < 4:
            book.push(null, i * 1_000_000 + 100, 0., score(-50_000.))
        book.push(alternate_lane, i * 1_000_000 + 200, 0., score(400_000.))
    primary, different = book.donors(same, 5_000_000)
    assert len(primary) == len(different) == 3
    assert primary[0][0] == 2_000_000
    assert different[-1][0] == 3_000_100
    assert book.donors(same, 30_000_000) == (None, None)


def test_signed_matching_never_double_counts_or_folds():
    factors = [(0, 0, 0., -80_300., .2, .1), (1, 0, 0., -79_000., .2, .1)]
    assert matched(factors, [-79_900., 80_300., 50_000., 900.], 4550) == [0]
    assert matched(factors, [80_300., 79_000., 50_000., 900.], 4550) == []


def test_optimistic_budget_charges_cold_and_missing_positive_retries():
    factor = (0, 0, 0., 100_000., .2, .1)
    def row(cost, factors, picks):
        return dict(installed_cpu_ns=cost, sketch_cpu_ns=10, factors=factors,
                    picks={arm: picks for arm in ARMS} if picks else {},
                    proposal_cpu_ns={arm: 1 for arm in ARMS} if picks else {})

    ledger = [row(20, [], []), row(30, [], [-100_000.]), row(50, [factor], [100_000.]),
              row(90, [factor], [-100_000.])]
    result = summary(ledger)["by_arm"]["drift_pool"]["4550"]
    assert result["fallback_cpu_ns"] == 110
    assert result["oracle_floor_cpu_ns"] == 153
    assert result["matches_by_rank"] == {0: 1}
    assert result["counts"]["empty_lanes_with_proposals"] == 1
