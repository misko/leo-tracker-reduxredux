import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace as S

import numpy as np
import pytest

spec = importlib.util.spec_from_file_location("dsx_model_c", Path(__file__).with_name("model_c.py"))
core = importlib.util.module_from_spec(spec)
spec.loader.exec_module(core)


def context():
    from leo.analysis.regional_position_score import zero_sum_basis
    obs = S(times_s=np.array([0., 1.]), measured_hz=np.array([1., 2.]))
    bank = S(nodes_s=np.array([-30., 31.]), numbers=np.array([1, 2]))
    model = S(clock_count=2, basis=zero_sum_basis(2), observations=obs, bank=bank)
    return S(model=model, vector=np.zeros(9), nuisance=np.array([1., 2., .3]),
             prior=S(radius_km=250.), observations=obs, bank=bank,
             train_mask=np.array([True, False]), fixed_c=False, source_id="synthetic")


def test_basin_trap_training_selection_and_fixed_total_budget(monkeypatch):
    ctx = context()
    calls = []
    def refit(context, vector, nuisance, **options):
        calls.append(options)
        # Deliberate local trap at the saved center; positive-position seed
        # discovers another training basin without any reference coordinates.
        value = 1. if vector[0] > 1 else 10.
        return dict(vector=vector, nuisance=nuisance,
                    diagnostics=dict(objective=value, accepted=True,
                                     stationarity=0., evaluations=options["max_evaluations"]))
    monkeypatch.setitem(sys.modules, "common", S(refit=refit))
    result = core.fit(ctx, max_evaluations=31, max_seconds=10)
    assert result["diagnostics"]["selected_basin"] == "position-ne"
    assert result["diagnostics"]["objective"] == 1
    assert sum(c["max_evaluations"] for c in calls) == 31
    assert result["diagnostics"]["evaluations"] == 31
    assert len(calls) == 6 and all(c["max_seconds"] <= 10 for c in calls)


@pytest.mark.parametrize("failure", [TimeoutError, RuntimeError, ValueError])
def test_failed_start_strict_selection_and_lower_rejected_warning(monkeypatch, failure):
    calls = []
    def refit(context, vector, nuisance, **options):
        calls.append(1)
        if len(calls) == 1:
            raise failure("bounded endpoint absent")
        return dict(vector=vector, nuisance=nuisance,
            diagnostics=dict(objective=float(len(calls)), accepted=len(calls) != 2,
                             stationarity=0. if len(calls) != 2 else 1., evaluations=2))
    monkeypatch.setitem(sys.modules, "common", S(refit=refit))
    result = core.fit(context(), max_evaluations=30)
    d = result["diagnostics"]
    assert not d["accepted"] and d["objective"] == 2 and d["strict_search_gap"] == 1
    assert d["strict_objective"] == 3
    assert d["evaluations"] == 15 and len(d["records"]) == 6
    assert d["records"][0]["accounting"] == "reserved-upper-bound"
    assert d["evaluation_accounting"] == "reserved upper bound for unreturned failures"


def test_no_held_cfo_access_feasible_starts_and_zero_c(monkeypatch):
    ctx = context()
    ctx.vector[:2] = [249., 0.]
    ctx.vector[6] = 50
    ctx.fixed_c = True
    initial = core.basins(ctx)
    ctx.observations.measured_hz[1] = 1e99
    altered = core.basins(ctx)
    for (_, v, n), (_, vv, nn) in zip(initial, altered, strict=True):
        np.testing.assert_array_equal(v, vv)
        np.testing.assert_array_equal(n, nn)
        assert v[6] == 0 and np.linalg.norm(v[:2]) <= ctx.prior.radius_km
        assert np.max(abs(v[7]+ctx.model.basis@v[8:])) <= 20
    def refit(context, vector, nuisance, **options):
        assert options["fixed_c"] and vector[6] == 0
        return dict(vector=vector, nuisance=nuisance,
            diagnostics=dict(objective=float(vector[0]**2), accepted=True,
                             evaluations=options["max_evaluations"]))
    monkeypatch.setitem(sys.modules, "common", S(refit=refit))
    a = core.fit(ctx, max_evaluations=6)
    ctx.observations.measured_hz[1] = -1e99
    b = core.fit(ctx, max_evaluations=6)
    np.testing.assert_array_equal(a["vector"], b["vector"])
    assert a["diagnostics"]["objective"] == b["diagnostics"]["objective"]


def test_deadline_prevents_calls_and_bad_count_fails_closed(monkeypatch):
    ctx = context()
    ctx.deadline = 0
    monkeypatch.setitem(sys.modules, "common", S(refit=lambda *a, **k: pytest.fail("expired")))
    result = core.fit(ctx)
    assert result["diagnostics"]["evaluations"] == 0
    assert not result["diagnostics"]["accepted"]
    del ctx.deadline
    def wrong(*args, **kwargs):
        return dict(vector=ctx.vector, nuisance=ctx.nuisance,
                    diagnostics=dict(evaluations=999, objective=1., accepted=True))
    monkeypatch.setitem(sys.modules, "common", S(refit=wrong))
    with pytest.raises(RuntimeError, match="quota"):
        core.fit(ctx)
