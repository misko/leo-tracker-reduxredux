"""Prove withheld values cannot nominate training tracks or bypass bilateral gates."""

from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/"reports/ALGO08/v3"))

from held_spatial_start import accepted, held_matches, split, wrapped


def test_whole_stereo_lanes_use_only_disjoint_authorized_measurements():
    rows = [dict(visit_index=visit, receiver_id=rx, edge="upper", channel=1+visit%2,
                 actual_rf_hz=11e9+visit%2, candidates=[(visit, rx)])
            for visit in range(20) for rx in (0, 1)]
    native = {"source": {"probes": rows}, "clock_anchor": {}}
    training, held, visits = split(native)
    assert visits == [4, 5, 14, 15]
    for a, b, original in zip(training["source"]["probes"], held["source"]["probes"], rows, strict=True):
        assert bool(a["candidates"]) != bool(b["candidates"])
        assert a["candidates"] + b["candidates"] == original["candidates"]


def test_holdout_motion_must_match_by_training_time_even_for_unnominated_ambiguity():
    track = dict(receiver=1, channel=2, rf_hz=11e9, times=[0., 8., 20.])
    observation = dict(receiver=1, channel=2, actual_rf_hz=11e9, time_s=7., measured_cfo_hz=150.)
    assert list(held_matches([track], {0: 7}, [observation])) == [0]
    assert not held_matches([track, dict(track, times=[1., 4., 10.])], {0: 7}, [observation])
    assert not held_matches([track], {0: 7}, [dict(observation, time_s=22.)])
    assert np.array_equal(wrapped([501, -501], 1000), [-499, 499])


def test_both_arms_and_every_challenger_require_independent_bilateral_gain():
    challenges = [dict(log_gain={"1": 2.5, "2": 3.}) for _ in range(4)]
    fit = dict(clearance_km=3., held_rms_hz={"1": 60., "2": 70.}, challengers=challenges)
    result = dict(arms={"c0": fit, "fitted_c": dict(fit)}, support=dict(coverage=.7, sigma_hz=40.,
         radio={"1": dict(rows=12, orbits=2), "2": dict(rows=13, orbits=3)}))
    assert not accepted(result)
    result["arms"]["fitted_c"]["challengers"] = [*challenges[:3], dict(log_gain={"1": 3., "2": -1.})]
    assert accepted(result) == ["fitted_c_weak_spatial_separation"]
