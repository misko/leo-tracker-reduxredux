"""Fake-port guard tests without model fits or recording access."""

import copy
import json

import pytest

from own_arm import repair_then_transition


def fit():
    return dict(vector=[1., 2., 0., 0., 0., 0., 0., 0.], objective=10.,
                converged=False, stop_reason="returned-best-state-nonstationary")


def audit(model, value, arm):
    good = value["objective"] != 10.
    return dict(objective=value["objective"], stationarity=0.0001 if good else .01,
                feasible=True, qualified=good, rf_arm=arm)


def test_same_arm_budget_and_explicit_downstream_both_arms():
    for arm in ("zero-c", "fitted-c"):
        original = fit()
        snapshot = copy.deepcopy(original)
        calls = []
        def bounded(model, vector, **options):
            assert options == dict(rf_arm=arm, fixed_position=True, slope_half_width_hz_s=60,
                                   maximum_seconds=5, maximum_iterations=200)
            assert vector == original["vector"]
            vector[2] = 7.
            value = fit(); value.update(vector=vector, objective=9.)
            return value, dict(solver_success=False, terminal={"preserved": True})
        def transition(model, value, point, actual_arm):
            calls.append((actual_arm, value["vector"][6], value["objective"]))
            assert value["converged"] and point == [1., 2.]
            return dict(status="promotion-unqualified")
        row = repair_then_transition(None, original, [1., 2.], arm,
                                     audit=audit, bounded=bounded, transition=transition)
        assert row["status"] == "own-arm-admitted"
        assert row["handoff"]["status"] == "promotion-unqualified"
        assert original == snapshot and calls == [(arm, 0., 9.)]
        assert row["repair"]["solver"]["terminal"] == {"preserved": True}


def test_already_qualified_skips_repair_and_ignores_original_solver_flag():
    original = fit(); original["objective"] = 9.
    def forbidden(*args, **kwargs):
        raise AssertionError("no repair for independently qualified original")
    row = repair_then_transition(None, original, [1., 2.], "zero-c", audit=audit,
                                 bounded=forbidden, transition=lambda *args: {"status": "qualified"})
    assert row["repair"] is None and row["admitted"]["converged"]


@pytest.mark.parametrize("change", ["position", "c", "arm", "slope", "nan", "none", "unqualified", "worse"])
def test_failed_or_changed_candidate_never_reaches_transition(change):
    candidate = fit(); candidate["objective"] = 9.
    if change == "position": candidate["vector"][0] = 3.
    if change == "c": candidate["vector"][6] = 1.
    if change == "arm": candidate["rf_arm"] = "fitted-c"
    if change == "slope": candidate["vector"][3] = 61.
    if change == "nan": candidate["objective"] = float("nan")
    if change == "none": candidate = None
    if change == "unqualified": candidate["objective"] = 10.
    if change == "worse": candidate["objective"] = 11.
    def forbidden(*args):
        raise AssertionError("invalid candidate reached150")
    row = repair_then_transition(None, fit(), [1., 2.], "zero-c", audit=audit,
                                 bounded=lambda *args, **kwargs: (candidate, {"available": True}),
                                 transition=forbidden)
    assert row["admitted"] is None and row["handoff"] is None
    assert row["repair"]["solver"] == {"available": True}
    json.dumps(row, allow_nan=False)


def test_audit_failure_keeps_candidate_and_solver():
    candidate = fit(); candidate["objective"] = 9.
    def bad_audit(model, value, arm):
        result = audit(model, value, arm)
        if value["objective"] == 9.: result["stationarity"] = float("inf")
        return result
    row = repair_then_transition(None, fit(), [1., 2.], "zero-c", audit=bad_audit,
                                 bounded=lambda *args, **kwargs: (candidate, {"available": True}),
                                 transition=lambda *args: pytest.fail("unexpected transition"))
    assert row["status"] == "own-arm-repair-failed"
    assert row["repair"]["fit"] == candidate
    assert row["repair"]["audit"]["stationarity"] == "inf"
    json.dumps(row, allow_nan=False)
