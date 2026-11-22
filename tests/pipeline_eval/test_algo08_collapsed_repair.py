from types import SimpleNamespace

import numpy as np
import pytest

from leo.analysis.localization_v3 import event_position, family_weighting
from tools.pipeline_eval.variants import algo08_collapsed_repair as repair


def gate(component, compatible):
    return dict(component=component, compatible=compatible)


def record(tracks, entries, *, settled=True):
    return dict(gates={"tracks": tracks}, linear_gates=entries,
                endpoint_east_north_km=np.zeros(2), phase_reference=np.zeros(2),
                final_phase_change_s=0.001 if settled else .02)


@pytest.fixture
def proposal(monkeypatch):
    scan = SimpleNamespace(tracks=[dict(receiver=rx, channel=ch) for rx, ch in (
        (1, 1), (2, 1), (1, 2), (2, 2), (1, 2), (2, 2), (1, 1),
    )])
    rows = [dict(component=component, candidate_index=label) for component, label in (
        ("a", 0), ("b", 0), ("c", 1), ("d", 1),
    )]
    base = SimpleNamespace(rows=rows, members=list(range(len(rows))), supported=[0, 1],
                           slices=[slice(2 * i, 2 * i + 2) for i in range(4)], labels=[0, 1])
    entries = [dict(component=component, track_index=index, candidate_index=1,
                    points=6, alias=0, cross_receiver_curved_support=True)
               for component, index in (("p1", 4), ("p2", 5), ("p3", 6))]
    pair = {
        "c0": record([gate("a", False), gate("b", True)], [gate("p1", False), gate("p2", True)]),
        "fitted_c": record([gate("a", True), gate("b", False)], [gate("p1", True), gate("p2", False)]),
    }
    value = dict(scan=scan, node={}, keep=np.ones(8, bool), entries=entries, arms=pair,
                 model=dict(shrinkage=0.5), powers=[.5] * 4, means=[-1.0] * 2)
    monkeypatch.setattr(repair, "problem", lambda *_: base)

    def confidence(scan, node, keep, baseline):
        assert baseline["arms"]["c0"]["record"] is pair["c0"]
        assert np.array_equal(keep, [False] * 4 + [True] * 4)
        return np.ones(4)

    def widths(scan, labels):
        assert labels == [0, 1]
        return np.ones(2), [dict(old_new_alignment_s=None, previous_epoch_gap_s=None,
                                 sigma_s=1.0) for _ in labels]

    monkeypatch.setattr(family_weighting, "confidence_for", confidence)
    monkeypatch.setattr(repair, "phase_widths", widths)
    return value


@pytest.mark.parametrize("acceptable", [False, True])
def test_one_refit_uses_the_exact_union_and_original_paired_gate(proposal, monkeypatch, acceptable):
    calls = []

    def fit(scan, node, remaining, arm, powers, means, model, events, entries):
        assert scan is proposal["scan"] and node is proposal["node"]
        assert np.array_equal(remaining, [False] * 4 + [True] * 4)
        assert np.array_equal(powers, [0.2, 0.2, 1., 1.])
        assert np.array_equal(means, [0., 0.])
        assert [entry["component"] for entry in entries] == ["p3"]
        assert entries[0]["cross_receiver_curved_support"]
        assert model is proposal["model"] and not events
        calls.append(arm)
        return record([gate("c", True), gate("d", True)], [gate("p3", True)],
                      settled=acceptable or arm == "c0")

    monkeypatch.setattr(event_position, "refit", fit)
    result, info = repair.repair_pair(proposal, 12.5)
    assert calls == ["c0", "fitted_c"]
    assert info["refits"] == 1
    assert info["removed_curved"] == ["a", "b"] and info["removed_curved_points"] == 4
    assert info["removed_predictive"] == ["p1", "p2"] and info["removed_predictive_points"] == 12
    assert info["accepted"] == acceptable and (result is not None) == acceptable
    assert proposal["keep"].all() and len(proposal["entries"]) == 3


def test_no_refit_if_a_surviving_predictive_entry_loses_curved_support(proposal, monkeypatch):
    proposal["entries"][-1]["candidate_index"] = 0
    monkeypatch.setattr(event_position, "refit", lambda *_: pytest.fail("unexpected paired refit"))
    result, info = repair.repair_pair(proposal, 12.5)
    assert result is None and info["reason"] == "unqualified_predictive_support"
    assert info["refits"] == 0 and len(proposal["entries"]) == 3


def test_no_repair_for_phase_failure_without_incompatible_tracks(proposal, monkeypatch):
    for row in proposal["arms"].values():
        row["gates"]["tracks"] = [gate("a", True)]
        row["linear_gates"] = [gate("p1", True)]
    monkeypatch.setattr(event_position, "refit", lambda *_: pytest.fail("unexpected paired refit"))
    result, info = repair.repair_pair(proposal, 12.5)
    assert result is None and info["reason"] == "no_failed_tracks" and info["refits"] == 0


def test_prefit_gates_each_arm_once_at_its_own_anchor(monkeypatch, proposal):
    incumbent = dict(proposal, node=object(), arms={
        "c0": dict(endpoint_east_north_km=[1., 2.], phase_reference=[.2, .3]),
        "fitted_c": dict(endpoint_east_north_km=[4., 5.], phase_reference=[.4, .5]),
    })
    proposal["means"] = [.1, .6]
    calls = []

    def problem(scan, node, arm, keep):
        return SimpleNamespace(labels=[2, 1] if node is incumbent["node"] else [0, 1])

    def make(scan, node, keep, arm, reference, powers, means, model, events):
        assert node is proposal["node"] and keep is proposal["keep"]
        assert reference.tolist() == [.1, incumbent["arms"][arm]["phase_reference"][1]]
        return SimpleNamespace(arm=arm)

    def summarize(model, point, entries):
        assert point == incumbent["arms"][model.arm]["endpoint_east_north_km"]
        assert entries is proposal["entries"]
        calls.append(model.arm)
        return {"point": point}

    monkeypatch.setattr(repair, "problem", problem)
    monkeypatch.setattr(event_position, "make_event_problem", make)
    monkeypatch.setattr(event_position, "attach_event_predictive", lambda *_: None)
    monkeypatch.setattr(event_position, "cached", lambda *_: None)
    monkeypatch.setattr(event_position, "summary", summarize)

    def refit_once(offered, half_width_km, *, fit_unchanged):
        assert fit_unchanged and half_width_km == 12.5
        assert offered["arms"] == {
            "c0": {"point": [1., 2.]}, "fitted_c": {"point": [4., 5.]},
        }
        assert calls == ["c0", "fitted_c"]
        return offered, {"accepted": True}

    monkeypatch.setattr(repair, "repair_pair", refit_once)
    result, info = repair.screen_and_fit(incumbent, proposal, 12.5)
    assert result is not None and info["accepted"]
