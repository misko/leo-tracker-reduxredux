from copy import deepcopy

import pytest

import score_dual_track_attribution as subject
from test_dual_track_attribution import point


def setup(monkeypatch):
    p = point()
    for row in p["tracks"]:
        row["variants"]["old"] = deepcopy(row["variants"]["dual"])
        row["variants"]["detection"] = deepcopy(row["variants"]["dual"])
    p["variant_scores"].update(old=deepcopy(p["variant_scores"]["dual"]),
                               detection=deepcopy(p["variant_scores"]["dual"]))
    item = {"labels": ["D", "old", "detection", "dual"], "coordinate": [1., 2.],
            "source": {}, "diagnostic": p, "aggregate_parity": {"passed": True}}
    monkeypatch.setattr(subject.runner, "fixed_inventory", lambda branch: [item])
    monkeypatch.setattr(subject.runner, "aggregate_parity", lambda *args: {"passed": True})
    payload = {"session_id": "scan", "branches": {
        prior: {"positions": [deepcopy(item)]} for prior in subject.runner.base.PRIORS}}
    source = {"branches": {prior: {} for prior in subject.runner.base.PRIORS}}
    return payload, source


def test_all_priors_pairs_variants_and_exact_zero_deltas(monkeypatch):
    payload, source = setup(monkeypatch)
    result = subject.analyze(payload, source)
    assert len(result) == 18
    assert all(row["totals"]["delta_joint"] == 0 for row in result)


def test_rejects_missing_prior(monkeypatch):
    payload, source = setup(monkeypatch); payload["branches"].pop("reno")
    with pytest.raises(ValueError, match="priors"):
        subject.analyze(payload, source)


def test_rejects_point_outside_saved_inventory(monkeypatch):
    payload, source = setup(monkeypatch)
    payload["branches"]["reno"]["positions"][0]["coordinate"] = [2., 3.]
    with pytest.raises(ValueError, match="point/source"):
        subject.analyze(payload, source)
