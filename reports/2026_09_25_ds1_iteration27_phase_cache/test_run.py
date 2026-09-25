from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import MethodType, SimpleNamespace

import numpy as np
import pytest


def module():
    path = Path(__file__).with_name("run.py")
    spec = importlib.util.spec_from_file_location("i27_test", path)
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = value
    spec.loader.exec_module(value)
    return value


def test_plan_freezes_cache_and_iteration26_scoring_contract():
    m = module()
    plan = m.verified_json(Path(__file__).with_name("plan.json"))
    m.validate_plan(plan)
    assert plan["data_policy"]["truth_used"] is False and plan["data_policy"]["held_used"] is False
    assert plan["smoke_gates"]["posterior_material_node_minimum_discrete_mass"] == 1e-6
    assert plan["phase_state_cache"]["schema"] == "ds1-phase-state-cache/v1"
    assert {"tau_ns", "rate_node_bits", "phase_node_bits", "per_row_correction_ns"} < set(
        plan["phase_state_cache"]["key_fields"]
    )
    assert plan["sealed_stencil"]["translation_or_refinement"] is False


def test_local_four_knot_barycentric_cubic_and_no_extrapolation():
    m = module()
    knots = np.asarray([-1.0, 0.0, 1.0, 2.0, 3.0])
    values = np.stack([np.full((2, 3), x**3 - 2 * x + 4) for x in knots])
    query = np.asarray([-1.0, -0.25, 0.5, 1.75, 3.0])
    actual = m.barycentric_states(knots, values, query)
    assert np.allclose(actual[:, 0, 0], query**3 - 2 * query + 4, atol=1e-12)
    with pytest.raises(ValueError, match="outside support"):
        m.barycentric_states(knots, values, np.asarray([3.01]))


def test_session_source_age_convention_is_constant_and_phase_is_rate_times_age():
    m = module()
    seen = []

    class Cache:
        entries = {("g", "s", "7"): SimpleNamespace(knots=np.asarray([-10.0, -1.0, 0.0, 10.0]))}

        def states(self, context, sid, source, phase, *, direct=False):
            seen.append(phase.copy())
            p = np.zeros((len(phase), 2, 3))
            p[:, :, 0] = phase[:, None]
            return p, np.zeros_like(p)

    orbit = SimpleNamespace(doppler=lambda receiver, p, v, search: p[:, 0])
    data = SimpleNamespace(
        session=np.asarray(["s", "s"]), source=np.asarray(["7", "7"]), age_h=np.asarray([4.0, 4.0])
    )
    context = SimpleNamespace(group="g", sessions=("s",), data=data, orbit=orbit, search=object())
    e = m.SourceEvaluator.__new__(m.SourceEvaluator)
    e.context = context
    e.source = "7"
    e.receiver = np.zeros(3)
    e.cache = Cache()
    e.rows = np.asarray([0, 1])
    e.local = {0: 0, 1: 1}
    prediction = e.predictions(np.asarray([0.5, 1.0]))
    assert np.allclose(seen[0], [2.0, 4.0])
    assert np.allclose(prediction[:, 0], [2.0, 4.0])
    data.age_h = np.asarray([4.0, 4.01])
    with pytest.raises(ValueError, match="causal age"):
        e.predictions(np.asarray([0.6]))


def test_mode_enumeration_never_returns_core_endpoints():
    m = module()
    evaluator = m.SourceEvaluator.__new__(m.SourceEvaluator)
    evaluator.maximum_age_h = 1.0

    def evaluate(self, rates, *, losses=True, direct_mask=None):
        return -np.asarray(rates, float), None

    evaluator.evaluate = MethodType(evaluate, evaluator)
    modes = evaluator.modes()
    bound = 16 * m.SIGMA
    assert modes and all(-bound < row["rate_s_h"] < bound for row in modes)


def test_transformed_tail_quadrature_is_direct_and_normalizes_prior():
    m = module()
    evaluator = m.SourceEvaluator.__new__(m.SourceEvaluator)
    evaluator.maximum_age_h = 20.0
    evaluator.context = SimpleNamespace(sessions=("s",))
    direct = []

    def evaluate(self, rates, *, losses=True, direct_mask=None):
        direct.append(np.asarray(direct_mask, bool))
        values = 0.5 * (np.asarray(rates, float) / m.SIGMA) ** 2
        return values, np.zeros((len(values), 1)) if losses else None

    evaluator.evaluate = MethodType(evaluate, evaluator)
    result = evaluator.integrate(12.0, 0.0125)
    expected = 0.5 * np.log(2 * np.pi) + np.log(m.SIGMA)
    assert (
        np.sum(direct[0]) == 2 * m.TAIL_ORDER
        and abs(result["log_normalizer"] - expected) < 1e-10
        and result["tail_mass"] < 1e-30
    )


def test_sealed_outputs_are_truthful_and_stencil_is_conditional():
    m = module()
    here = Path(__file__).parent
    smoke_path = here / "smoke.json"
    if not smoke_path.exists():
        pytest.skip("sealed smoke not generated yet")
    smoke = m.verified_json(smoke_path)
    assert (
        smoke["truth_used"] is False
        and smoke["held_used"] is False
        and smoke["geographic_search_run"] is False
    )
    stencil_path = here / "stencil.json"
    if smoke["gate"]["passed"]:
        assert stencil_path.exists()
        stencil = m.verified_json(stencil_path)
        assert (
            stencil["anchor_smoke_digest"] == m.digest(smoke_path)
            and len(stencil["cells"]) == 9
            and len(stencil["leave_one_session_reranks"]) == 12
        )
    else:
        assert not stencil_path.exists()
