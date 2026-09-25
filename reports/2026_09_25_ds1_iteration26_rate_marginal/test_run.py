from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import MethodType, SimpleNamespace

import numpy as np


def module():
    path = Path(__file__).with_name("run.py")
    spec = importlib.util.spec_from_file_location("i26_test", path)
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = value
    spec.loader.exec_module(value)
    return value


def test_plan_freezes_train_only_material_node_gate() -> None:
    m = module()
    plan = m.verified_json(Path(__file__).with_name("plan.json"))
    assert plan["data_policy"]["held_used"] is False
    assert plan["data_policy"]["truth_used"] is False
    assert plan["smoke_gates"]["posterior_material_node_minimum_discrete_mass"] == 1e-6
    assert plan["smoke_gates"]["exact_sgp4_nodes"].startswith("zero, every refined mode")
    assert plan["posterior"]["endpoints_are_fitted_candidates"] is False


def test_mode_enumeration_never_returns_core_endpoints() -> None:
    m = module()
    evaluator = m.SourceEvaluator.__new__(m.SourceEvaluator)
    evaluator.maximum_age_h = 1.0

    def evaluate(self, rates, *, losses=True):
        # Monotone across the core: the fallback must still select an interior
        # grid point rather than silently treating a quadrature endpoint as a mode.
        values = -np.asarray(rates, float)
        return values, None

    evaluator.evaluate = MethodType(evaluate, evaluator)
    modes = evaluator.modes()
    bound = 16.0 * m.SIGMA
    assert modes
    assert all(-bound < row["rate_s_h"] < bound for row in modes)


def test_transformed_tail_quadrature_normalizes_gaussian_prior() -> None:
    m = module()
    evaluator = m.SourceEvaluator.__new__(m.SourceEvaluator)
    evaluator.maximum_age_h = 20.0
    evaluator.context = SimpleNamespace(sessions=("s",))

    def evaluate(self, rates, *, losses=True):
        values = 0.5 * (np.asarray(rates, float) / m.SIGMA) ** 2
        numerators = np.zeros((len(values), 1)) if losses else None
        return values, numerators

    evaluator.evaluate = MethodType(evaluate, evaluator)
    result = evaluator.integrate(12.0, 0.0125)
    expected = 0.5 * np.log(2.0 * np.pi) + np.log(m.SIGMA)
    assert abs(result["log_normalizer"] - expected) < 1e-10
    assert result["tail_mass"] < 1e-30
    assert abs(result["posterior_mean_s_h"]) < 1e-14
    assert abs(result["posterior_sd_s_h"] - m.SIGMA) < 1e-10


def test_smoke_is_sealed_truthful_no_go() -> None:
    m = module()
    smoke = m.verified_json(Path(__file__).with_name("smoke.json"))
    assert smoke["complete"] is True
    assert smoke["truth_used"] is False
    assert smoke["held_used"] is False
    assert smoke["geographic_search_run"] is False
    assert smoke["gate"]["passed"] is False
    assert smoke["gate"]["criteria"]["exact_sgp4_error"] is False
    assert smoke["maximum_exact_sgp4_error_hz"] > 0.2
    assert (
        smoke["explicit_source_68739"]["exact_audit"]["maximum_absolute_prediction_error_hz"] < 0.2
    )
