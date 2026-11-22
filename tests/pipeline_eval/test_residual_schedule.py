import pytest

from tools.pipeline_eval.variants.experimental.residual_schedule import Replay, RESIDUAL_HORIZON


def metadata(counter, receiver=0, rf=11e9):
    return dict(valid_start_counter=counter, receiver_id=receiver, channel=3, actual_rf_hz=rf)


def factor(rank, margin=0.1):
    return dict(candidate_rank=rank, fractional_tracking_cfo_hz=1000. * rank,
                fractional_margin=margin)


def replay(policy, counter, choices, **lane):
    return policy.visit(metadata(counter, **lane),
                        lambda full: choices if full else [f for f in choices if f["candidate_rank"] == 0])


def test_sentinels_count_every_admitted_opportunity_and_hide_residuals():
    policy = Replay("conditional")
    assert replay(policy, 0, [])[0]
    decision, factors, selected = replay(policy, 1, [factor(1, .3), factor(0)])
    assert decision is False and factors == [factor(0)] and selected == []
    assert not policy.last_residual
    assert replay(policy, 1, [], receiver=1)[0]
    assert replay(policy, 2, [], rf=12e9)[0]
    assert not replay(policy, 2, [factor(1)])[0]
    assert replay(policy, 3, [factor(1)])[0]


def test_real_rank_one_only_seeds_horizon_and_is_not_promoted_to_rank_zero():
    policy = Replay("conditional")
    full, observed, chosen = replay(policy, 0, [factor(1)])
    assert full and observed == [factor(1)] and not chosen
    assert replay(policy, 1, [])[0]
    assert replay(policy, RESIDUAL_HORIZON, [])[0]  # Inclusive horizon.
    assert replay(policy, RESIDUAL_HORIZON + 1, [])[0]  # Sentinel.
    assert not replay(policy, RESIDUAL_HORIZON + 2, [factor(1)])[0]
    assert replay(Replay("primary-only"), 0, [factor(1)]) == (False, [], [])


def test_only_independently_observed_residuals_extend_the_horizon_and_continuation():
    policy = Replay("conditional")
    second = 10_000_000
    for t in range(4):
        use_residual, observed, selected = replay(policy, t * second, [factor(1)])
        assert use_residual and observed == [factor(1)]
    assert selected == [factor(1)]
    assert replay(policy, 3 * second + RESIDUAL_HORIZON, [])[0]
    assert not replay(policy, 3 * second + RESIDUAL_HORIZON + 1, [factor(1)])[0]
    assert policy.last_residual[(0, 3, 11e9)] == 3 * second


def test_hidden_factor_or_duplicate_rank_is_an_integrity_failure():
    with pytest.raises(ValueError, match="skipped residual"):
        Replay("primary-only").visit(metadata(0), lambda _: [factor(1)])
    with pytest.raises(ValueError, match="distinct factors"):
        Replay("always-two").visit(metadata(0), lambda _: [factor(0), factor(0)])
