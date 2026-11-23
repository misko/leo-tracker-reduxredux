from importlib import import_module
from pathlib import Path

import pytest


@pytest.fixture
def repair(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    return import_module("blind_joint_repair")


def test_repair_caps_tracks_and_both_observation_roles(repair):
    admitted = dict(tracks=(100, 5), curved=(1000, 50), predictive=(200, 10))
    assert repair.small_rejection(admitted)
    assert not repair.small_rejection(dict(admitted, tracks=(100, 6)))
    assert not repair.small_rejection(dict(admitted, curved=(1000, 51)))
    assert not repair.small_rejection(dict(admitted, predictive=(200, 11)))
    assert not repair.small_rejection(dict(tracks=(100, 0), curved=(1000, 0), predictive=(0, 0)))
    assert repair.small_rejection(dict(admitted, predictive=(0, 0)))


def test_repair_requires_track_to_pass_both_arms(repair):
    arms = {}
    for arm, curved, linear in (("c0", ["a"], []), ("fitted_c", ["b"], ["p"])):
        arms[arm] = dict(gates={"tracks": [dict(component=t, compatible=False) for t in curved]},
                         linear_gates=[dict(component=t, compatible=False) for t in linear])
    assert repair.failed_union(arms) == ({"a", "b"}, {"p"})


def test_repair_drops_predictive_only_when_failed_or_without_curved_support(repair):
    tracks = [dict(receiver=1, channel=4), dict(receiver=2, channel=6), dict(receiver=1, channel=8)]
    initial = [dict(component=key, track_index=i, candidate_index=sat)
               for i, (key, sat) in enumerate((("supported", 8), ("unknown_family", 55), ("orphan_band", 8)))]
    groups = {8: {(1, 3), (2, 8)}}
    assert repair.retained_entries(initial, set(), groups, tracks) == [dict(initial[0], cross_receiver_curved_support=True)]
    assert repair.retained_entries(initial, {"supported"}, groups, tracks) == []
