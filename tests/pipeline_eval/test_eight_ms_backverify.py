"""Check that recheck cost includes complete signed members and other-row impact."""

import importlib
from pathlib import Path

import pytest


@pytest.fixture
def trial(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    return importlib.import_module("eight_ms_backverify")


def test_member_influence_excludes_direct_removal(trial):
    base = [(True, ("a", "b", "c"))]
    same = [(False, ("b", "c"))]
    assert trial.other_impact(base, same, "a") == dict(other_assignment_removed=0, other_assignment_gained=0,
                                                        other_regrouped=0, other_curvature_changed=2, influence=0)
    shifted = [(False, ("b", "d"))]
    assert trial.other_impact(base, shifted, "a") == dict(other_assignment_removed=1, other_assignment_gained=1,
                                                           other_regrouped=1, other_curvature_changed=1, influence=3)


def test_two_antenna_calls_charge_one_full_member_and_index(trial):
    members = [(22, 7, {0: 100, 1: 90}), (30, 11, {2: 98, 3: 93})]
    assert trial.storage_footprint(members, {2}) == dict(visits=1, members=1, compressed_bytes=30,
                                                         index_bytes=11, decoded_bytes=191, requested_stereo_bytes=98)
    audits = trial.rate_report([{"visit": 2}, {"visit": 2}], members,
                                dict(restart_12s=.001, restart_20s=.002, mixed_saving_s=.003))
    assert audits["lanes"] == 2 and audits["storage"]["visits"] == 1
    assert audits["restarts"]["12ms"]["required_decoded_bytes_per_s"] == pytest.approx(191000.)
    assert audits["restarts"]["20ms"]["required_decoded_bytes_per_s"] is None


def test_storage_audit_rejects_missing_and_duplicated_visits(trial):
    with pytest.raises(ValueError, match="did not match"):
        trial.storage_footprint([(22, 7, {0: 100})], {1})
    with pytest.raises(ValueError, match="multiple members"):
        trial.storage_footprint([(22, 7, {0: 100}), (21, 4, {0: 100})], {0})
