from types import SimpleNamespace

import numpy as np
import pytest

from reports.ALGO08.v3 import provisional_salvage as p
from reports.ALGO08.v3 import blind_joint_finish as joint
from reports.ALGO08.v3.blind_joint_finish import drop_failing


def fixture():
    scan = SimpleNamespace(search_region=SimpleNamespace(half_width_km=12.5))
    rows = [dict(component="incumbent", candidate_index=0, candidate_norad=200),
            dict(component="salvage", candidate_index=1, candidate_norad=100),
            dict(component="other", candidate_index=2, candidate_norad=300)]
    problem = SimpleNamespace(rows=rows, slices=[slice(0, 1), slice(1, 3), slice(3, 5)], alias=[0, -1, 1],
                              calculate=lambda point: {"negative_twice_elbo": 3 - point[0]})
    initial = np.array([True, False, False, False, False])
    expanded = np.ones(5, dtype=bool)
    support = dict(past_distribution_qualified=True, salvage=[
        dict(component="salvage", selected=dict(norad=100, candidate_index=1, alias=-1, start_index=0, stop_index=2, points=2)),
        dict(component="other", selected=dict(norad=300, candidate_index=2, alias=1, start_index=0, stop_index=2, points=2)),
    ])
    return scan, problem, initial, expanded, support


def gate(*rows):
    return dict(tracks=[dict(component=name, compatible=passing, observation_ids=ids) for name, passing, ids in rows])


def test_unchanged_gate_requires_original_survivors_and_confirms_subset(monkeypatch):
    scan, problem, initial, expanded, support = fixture()
    subset = object()
    calls = []

    def fit(base, point, *, iterations):
        assert base is problem and iterations == 48
        calls.append(point.tolist())
        return dict(parameters=[1., 0.], stopped="small_bounded_step")

    def build(scan, node, selected, point, refs, model):
        assert selected.tolist() == [True, True, True, False, False]
        return subset, 1, 2

    clean = gate(("incumbent", True, ["a"]), ("salvage", True, ["b", "c"]))
    measurements = gate(("incumbent", True, ["a"]), ("salvage", True, ["b", "c"]), ("other", False, ["d", "e"]))
    monkeypatch.setattr(p.position, "fit", fit)
    monkeypatch.setattr(p.conservative_recovery, "retained_metrics", lambda base, point: clean if base is subset else measurements)
    audit = {}
    out = p.refine(scan, None, (problem, 0, 0), initial, expanded, initial, np.zeros(2), None, None,
                   support, audit, build=build, drop=drop_failing)
    assert calls == [[0., 0.]]
    assert audit["independently_supported_gain"] == 2 and audit["same_support_objective"] == [3., 2.]
    assert audit["postfit_rejected"] == ["other"] and audit["subset_rejected"] == []
    assert out[0].tolist() == [True, True, True, False, False] and out[1] is subset


def test_no_fit_without_qualified_changed_support_or_exact_signed_nomination(monkeypatch):
    scan, problem, initial, expanded, support = fixture()
    monkeypatch.setattr(p.position, "fit", lambda *_args, **_kwargs: pytest.fail("must use zero fit budget"))
    audit = {}
    assert p.refine(scan, None, (problem, 0, 0), initial, expanded, expanded, np.zeros(2), None, None,
                    support, audit, build=None, drop=drop_failing) is None
    assert audit["fit_calls"] == 0
    support["salvage"][0]["selected"]["alias"] = 1
    assert p.refine(scan, None, (problem, 0, 0), initial, expanded, initial, np.zeros(2), None, None,
                    support, audit, build=None, drop=drop_failing) is None
    assert audit["reason"] == "unbound_signed_salvage_support"


@pytest.mark.parametrize(("endpoint", "metrics", "reason"), [
    ([0., 0.], None, "no_strict_same_support_objective_improvement"),
    ([13., 0.], None, "invalid_position"),
    ([1., 0.], gate(("incumbent", False, ["a"]), ("salvage", True, ["b", "c"])), "original_support_lost_or_no_rescued_gain"),
])
def test_unsafe_fit_reverts_without_a_second_fit(monkeypatch, endpoint, metrics, reason):
    scan, problem, initial, expanded, support = fixture()
    monkeypatch.setattr(p.position, "fit", lambda *_args, **_kwargs: dict(parameters=endpoint, stopped="small_bounded_step"))
    monkeypatch.setattr(p.conservative_recovery, "retained_metrics", lambda *_: metrics)
    audit = {}
    assert p.refine(scan, None, (problem, 0, 0), initial, expanded, initial, np.zeros(2), None, None,
                    support, audit, build=None, drop=drop_failing) is None
    assert audit["fit_calls"] == 1 and audit["reason"] == reason and audit["status"] == "reverted"


def test_original_paired_gate_failure_reverts_owners_and_seed(monkeypatch):
    scan, base, initial, expanded, _ = fixture()
    seed, moved = np.zeros(2), np.array([1., 0.])
    original_gate = gate(("incumbent", True, ["a"]), ("salvage", False, ["b", "c"]),
                         ("other", False, ["d", "e"]))
    base.keep = expanded
    incumbent = SimpleNamespace(rows=base.rows, slices=base.slices, keep=initial)
    monkeypatch.setattr(joint.v5_core, "scan_context", lambda *_: scan)
    monkeypatch.setattr(joint, "history_model", lambda *_: (None, True))
    monkeypatch.setattr(joint, "build_at", lambda *args: (base if args[2] is None or args[2].all() else incumbent, None, None))
    monkeypatch.setattr(joint.conservative_recovery, "retained_metrics", lambda *_: original_gate)
    monkeypatch.setattr(joint.conservative_recovery, "salvage", lambda *_: (None, expanded, []))
    monkeypatch.setattr(joint, "select_entries", lambda *_: [])
    finished = []

    def fake_finish(scan, node, selected, problem, powers, means, model, entries, point, region, audit):
        finished.append((selected.tolist(), point.tolist()))
        return "old fit" if selected is not expanded else "rejected", selected is not expanded

    monkeypatch.setattr(joint, "finish_pair", fake_finish)
    rescue = lambda *_args, **_kwargs: (expanded, base, None, None, moved, original_gate)
    audit = {}
    result = joint.propose({"status": "inputs_prepared", "noise": []}, scan.search_region, None, audit,
                           cold_start=lambda *_: (None, seed, {}, {}), rescue=rescue)
    assert result == ("old fit", None)
    assert finished == [(expanded.tolist(), moved.tolist()), (initial.tolist(), seed.tolist())]
    assert audit["provisional_salvage"]["reason"] == "original_paired_gate"
