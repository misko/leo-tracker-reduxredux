from pathlib import Path
import sys

import numpy as np
import pytest


RESEARCH = Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"
sys.path.insert(0, str(RESEARCH))
try:
    from local_future_repair import PERIOD, extend_track, lift_for, nominate, preserved
    from local_future_repair_oracle import overlap
finally:
    sys.path.remove(str(RESEARCH))


def sample(oid, time, *, rf=11e9):
    return dict(observation_id=oid, time_s=time, receiver=1, channel=8,
                actual_rf_hz=rf, measured_cfo_hz=100., fractional_margin=.1)


def test_targets_require_an_owned_anchor_on_the_exact_stream_in_range():
    track = dict(key="g", receiver=1, channel=8, rf_hz=11e9,
                 observation_ids=["owned", "unowned"], times=np.array([10., 30.]), values=np.array([10., 20.]))
    before = {"g": ("conditional", 9, frozenset({"owned"}))}
    okay, absent = sample("new", 2.), sample("distant", 30.)
    assert list(nominate([track], before, [okay, absent, sample("different", 8., rf=12e9)])) == [(0, "conditional", okay)]
    with pytest.raises(ValueError, match="overlaps"):
        list(nominate([track], before, [sample("owned", 10.)]))


def test_both_calibrations_must_agree_on_signed_lift_and_doppler_gate():
    assert lift_for([(-PERIOD+2, 1., 0.), (-PERIOD+15, 0., 5.)]) == 1
    assert lift_for([(-PERIOD+2, 1., 0.), (2., 1., 0.)]) is None
    assert lift_for([(449., 10., 0.), (451., 10., 0.)]) is None
    assert lift_for([(1., -1., 0.), (1., 1., 0.)]) is None


def test_update_reorders_without_regraphing_or_replacing_prior_measurements():
    original = dict(key="g", pieces=[{"fixed": True}], observation_ids=["old0", "old1"],
                    times=np.array([10., 20.]), values=np.array([300., 400.]))
    updated = extend_track(original, [(sample("new", 9.), -1)])
    assert updated["observation_ids"] == ["new", "old0", "old1"]
    assert updated["values"].tolist() == [100.-PERIOD, 300., 400.]
    assert updated["times"].tolist() == [9., 10., 20.]
    assert original["observation_ids"] == ["old0", "old1"]
    assert updated["pieces"] is original["pieces"]
    with pytest.raises(ValueError, match="unique observations"):
        extend_track(original, [(sample("duplicate_epoch", 10.), 0)])


def test_ownership_guard_protects_every_owner_and_role():
    original = {"track": ("conditional", 75, frozenset({"old"}))}
    additions = {"track": {"new"}}
    assert preserved(original, {"track": ("conditional", 75, frozenset({"old", "new"}))}, additions)
    assert not preserved(original, {"track": ("predictive", 75, frozenset({"old", "new"}))}, additions)
    assert not preserved(original, {"track": ("conditional", 72, frozenset({"old", "new"}))}, additions)
    assert not preserved(original, {"track": ("conditional", 75, frozenset({"new"}))}, additions)


def test_oracle_distinguishes_future_additions_from_reassignment():
    native = {name: sample(name, time) for name, time in (("original", 10.), ("rescued", 12.), ("old_input", 15.))}
    first = [("original", 9, "conditional")]
    last = [("rescued", 9, "conditional"), ("old_input", 9, "predictive")]
    result = overlap(first, last, native, {"rescued"})
    assert result["counts"]["gained_future_only"] == 1
    assert result["counts"]["future_existing_same_lane_within_8s"] == 1
    assert result["counts"]["gained_already_forward_selected"] == 1
    assert result["ownership"]["lost"] == 1
