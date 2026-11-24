import pytest

from reports.ALGO08.v3.nomination_handoff_0255_publication import BASE_PIN, accepted_scope


def sample():
    trial = dict(qualified=True, before=BASE_PIN, producer={"cpu_ns": 1_000_000_000},
                 nomination_handoff={"scan_reuses": 1, "rank_reuses": 1, "prefixes_reused": 3},
                 scope_estimate_cpu_s=2.)
    cold = {"cold_clocks": {"cpu_s": 1.}}
    prior = {"candidate_traces": {"risk-route.json": {"solves": [{"lean_attempts": [cold]}]}}}
    return trial, prior


def test_partial_handoff_cannot_admit_the_post_holdout_candidate():
    trial, prior = sample()
    assert accepted_scope(trial, prior) == 2.
    trial["nomination_handoff"]["prefixes_reused"] = 2
    with pytest.raises(ValueError, match="all ordered prefixes"):
        accepted_scope(trial, prior)


def test_cost_of_the_new_producer_is_charged_before_admission():
    trial, prior = sample()
    trial["producer"]["cpu_ns"] = 2_200_000_000
    with pytest.raises(ValueError, match="less than one"):
        accepted_scope(trial, prior)
