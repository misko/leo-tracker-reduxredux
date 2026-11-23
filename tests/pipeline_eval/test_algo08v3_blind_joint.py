from importlib import import_module
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest


@pytest.fixture
def joint(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    return import_module("blind_joint_finish")


def test_joint_prune_keeps_original_support_without_admitting_new_points(joint):
    keep = np.array([True, False, False, True, True, False])
    rows = [dict(component="first"), dict(component="second"), dict(component="third")]
    gates = {"tracks": [{"component": "first", "compatible": True}, {"component": "second", "compatible": False}]}
    retained, bad = joint.drop_failing(keep, rows, [slice(0, 2), slice(2, 4), slice(4, 6)], gates)
    assert bad == ["second"]
    np.testing.assert_array_equal(retained, [True, False, False, False, True, False])
    np.testing.assert_array_equal(keep, [True, False, False, True, True, False])


def test_salvage_never_replaces_known_phase_reference(joint):
    nominal = {1: -3.}
    rows = [{"selected": item} for item in (
        dict(candidate_index=1, phase_s=10.), dict(candidate_index=7, phase_s=4.),
        None, dict(candidate_index=7, phase_s=6.),
    )]
    assert joint.rescued_references(nominal, rows) == {1: -3., 7: 5.}
    assert nominal == {1: -3.}


def test_predictive_rows_are_in_the_first_exact_fit_and_phase_has_a_fixed_cap(joint, monkeypatch):
    entries = [dict(points=5)]
    track = dict(active=True)
    calls = []

    def make(*_args):
        return SimpleNamespace(labels=[0], state=lambda _point: {"phases": np.array([9.])})

    def attach(problem, supplied, _powers):
        problem.linear = supplied

    def solve(problem, point, *, iterations):
        assert iterations == 48 and problem.linear is entries
        calls.append(point.copy())
        return {"parameters": point + np.array([.1, 0.])}

    monkeypatch.setattr(joint.event_position, "make_event_problem", make)
    monkeypatch.setattr(joint.event_position, "attach_event_predictive", attach)
    monkeypatch.setattr(joint.event_position, "cached", lambda p: p)
    monkeypatch.setattr(joint.position, "fit", solve)
    monkeypatch.setattr(joint.event_position, "summary", lambda _p, x, _e: {"endpoint": x})
    result = joint.arm_finish(track, {}, np.array([True]), "c0", np.array([0.]), None, None, None, entries, [0., 0.])
    assert len(calls) == 5 and result["final_phase_change_s"] == 0.
    np.testing.assert_allclose(result["endpoint"], [.5, 0.])
