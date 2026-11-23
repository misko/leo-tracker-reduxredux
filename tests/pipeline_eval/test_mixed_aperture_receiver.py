from reports.ALGO08.v3.mixed_aperture_receiver import RULE, StereoSchedule, strongest

import pytest


def test_period_is_per_exact_rf_and_unfilled_tail_is_untouched():
    schedule = StereoSchedule()
    target = dict(channel=3, edge="lower", lnb_lo_hz=9_750_000_000)
    mixed, independent = [], []
    for index in range(11):
        shared = dict(actual_if_center_hz=1_700_312_500., sample_start=2*index)
        mixed.append(schedule.visit("lower", target, shared))
        if index < 3:
            alternate = dict(shared, actual_if_center_hz=1_701_312_500.)
            independent.append(schedule.visit("lower", target, alternate))
    assert [mode for _, mode in mixed] == [*RULE, *RULE[:3]]
    assert independent == list(enumerate(RULE[:3]))
    assert [index for index, _ in mixed] == list(range(11))
    with pytest.raises(ValueError, match="Chronological"):
        schedule.visit("lower", target, shared)


def test_verified_rank_breaks_only_an_exact_margin_tie():
    primary = dict(fractional_margin=.05, candidate_rank=0, passed_fractional_margin_gate=True)
    residual = dict(fractional_margin=.05, candidate_rank=1, passed_fractional_margin_gate=True)
    assert strongest([residual, primary]) is primary
    large_residual = dict(residual, fractional_margin=.051)
    assert strongest([primary, large_residual]) is large_residual
    assert strongest([]) is None
    with pytest.raises(ValueError, match="unverified"):
        strongest([dict(residual, passed_fractional_margin_gate=False)])
