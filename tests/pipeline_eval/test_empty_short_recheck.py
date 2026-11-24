"""Measured empty-lane nominations use bounded base history and exact stream equality."""

from pathlib import Path
import sys

import pytest


sys.path[:0] = [str(Path(__file__).resolve().parents[2] / "reports" / "ALGO08" / "v3"),
               str(Path(__file__).resolve().parents[2])]
from empty_short_recheck import plan
from empty_short_recheck_score import compare, observation_id, stream, totals


def rows(observations):
    return [dict(visit_index=visit, receiver_id=radio, channel=channel, edge="lower",
                 actual_rf_hz=rf, valid_start_counter=counter,
                 candidates=[] if hz is None else [
                     dict(fractional_tracking_cfo_hz=hz, passed_fractional_margin_gate=True)])
            for visit, (counter, hz, radio, channel, rf) in enumerate(observations)]


def test_only_first_short_empty_after_three_actual_signed_votes():
    observations = [(int(t*1e7), -15000+500*t, 0, 2, 10e9) for t in (0, 1, 2, 3)]
    observations += [(40_000_000, None, 0, 2, 10e9), (50_000_000, None, 0, 2, 10e9)]
    got = plan(rows(observations), ["full", *["short"]*5])
    assert [(r["lane"], r["prior_votes"], r["triggered"]) for r in got] == [((4, 0), 3, True), ((5, 0), 0, False)]
    assert got[0]["last_positive_counter"] == 30_000_000


def test_full_empty_breaks_streak_and_cross_radio_or_frequency_contributes_nothing():
    observations = [(int(t*1e7), 0, 0, 2, 10e9) for t in (0, 1, 2, 3)]
    observations += [(40_000_000, None, 0, 2, 10e9), (50_000_000, None, 0, 2, 10e9),
                     (51_000_000, None, 1, 2, 10e9), (52_000_000, None, 0, 2, 10e9+1),
                     (53_000_000, None, 0, 3, 10e9)]
    got = plan(rows(observations), ["full", "short", "short", "short", "full", *["short"]*4])
    assert len(got) == 4 and all(not x["triggered"] for x in got)


@pytest.mark.parametrize(("empty", "expected"), [(80_000_000, True), (80_000_001, False)])
def test_eight_second_horizon_is_measured_from_the_empty(empty, expected):
    observations = [(0, 0), (10_000_000, 0), (20_000_000, 0), (30_000_000, 0), (empty, None)]
    got = plan(rows([(*sample, 0, 2, 10e9) for sample in observations]), ["short"]*5)
    assert got[0]["triggered"] is expected


def test_history_bound_includes_empty_attempts_and_requires_counter_order():
    opening = [(t*4_000_000, 0) for t in range(3)]
    observations = opening + [(t*4_000_000, None) for t in range(3, 15)] + [(60_000_000, 0), (64_000_000, None)]
    measured = rows([(*sample, 0, 2, 10e9) for sample in observations])
    got = plan(measured, ["short"]*len(measured))
    assert got[-1]["prior_opportunities"] == 11 and got[-1]["prior_votes"] == 0
    measured[-1]["valid_start_counter"] = 0
    with pytest.raises(ValueError, match="causal"):
        plan(measured, ["short"]*len(measured))


def test_oracle_duty_and_owners_use_the_same_original_antenna_opportunities():
    original = rows([(i*10_000_000, -50 if i in (1, 3) else None, 0, 2, 10e9) for i in range(5)])
    empties = [dict(lane=(i,0), stream=stream(r), counter=r["valid_start_counter"], triggered=i in (1, 2))
               for i, r in enumerate(original)]
    owner = observation_id("stable-original-session", original[1])
    score = compare(empties, {(i,0): r for i,r in enumerate(original)},
                    {"c0": {owner}, "fitted_c": set()}, "stable-original-session")
    assert [r["lane"] for r in score if r["even"]] == [(1,0), (3,0)]
    summaries = totals(score)
    assert summaries["checks"] == 2 and summaries["triggered_installed_empty"] == 1
    assert summaries["triggered_installed_lanes"] == 1 and summaries["evenly_installed_lanes"] == 2
    assert summaries["uniform_expected_installed_lanes"] == .8
    assert summaries["owners"]["c0"] == {"lost": 1, "triggered": 1, "evenly": 1, "uniform_expected": .4}
    assert summaries["owners"]["fitted_c"]["lost"] == 0

    empties[1]["counter"] += 1
    with pytest.raises(ValueError, match="different original hardware opportunity"):
        compare(empties, {(i,0): r for i,r in enumerate(original)},
                {"c0": {owner}, "fitted_c": set()}, "stable-original-session")
