from __future__ import annotations

from types import SimpleNamespace

import numpy as np
from compact_satellite_prune import iterative_prune


class FakeEvaluator:
    def __init__(self, scores):
        self.scores = scores
        self.calls = []

    def evaluate_bank(self, _parameters, satellites):
        bank = tuple(int(value) for value in satellites)
        self.calls.append(bank)
        objective = self.scores[bank]
        return {
            "objective": objective,
            "data_objective": objective,
            "prior_objective": 0.0,
            "raw_log_likelihood": -objective,
            "complexity_penalty": 0.0,
            "penalized_objective": objective,
            "support": {},
        }


def fit(objective_by_bank, success=True):
    def fitter(_data, parameters, satellites, _probability, _rf, *, budget_s):
        bank = tuple(int(value) for value in satellites)
        objective = objective_by_bank[bank]
        return {
            "parameters": np.asarray(parameters).copy(),
            "objective": objective,
            "data_objective": objective,
            "prior_objective": 0.0,
            "raw_log_likelihood": -objective,
            "success": success,
            "status": "projected_gradient_converged" if success else "time_limit",
            "budget_s": budget_s,
        }

    return fitter


def initial_fit(objective=20.0, success=True):
    return {
        "parameters": np.zeros(10),
        "objective": objective,
        "data_objective": objective,
        "prior_objective": 0.0,
        "raw_log_likelihood": -objective,
        "success": success,
    }


def test_pruning_rechecks_all_deletions_until_converged_local_minimum():
    data = SimpleNamespace(group=np.zeros(20, dtype=int))
    evaluator = FakeEvaluator(
        {
            (1, 2): 12.0,
            (0, 2): 15.0,
            (0, 1): 18.0,
            (2,): 13.0,
            (1,): 14.0,
        }
    )
    result = iterative_prune(
        data,
        evaluator,
        initial_fit(),
        np.array([0, 1, 2]),
        0.1,
        np.array([0.0]),
        budget_s=30.0,
        fitter=fit({(1, 2): 12.0}),
    )
    np.testing.assert_array_equal(result["satellite_indices"], [1, 2])
    assert result["accepted_deletion_count"] == 1
    assert result["termination"] == "no_improving_deletion"
    assert result["deletion_minimal"] is True
    assert len(result["iterations"]) == 2
    assert result["iterations"][1]["deletions_evaluated"] == 2


def test_nonconverged_final_fit_never_claims_deletion_minimality():
    data = SimpleNamespace(group=np.zeros(20, dtype=int))
    evaluator = FakeEvaluator({(1,): 12.0, (0,): 13.0})
    result = iterative_prune(
        data,
        evaluator,
        initial_fit(10.0, success=False),
        np.array([0, 1]),
        0.1,
        np.array([0.0]),
        budget_s=30.0,
        fitter=fit({}, success=False),
    )
    assert result["termination"] == "no_improving_deletion"
    assert result["deletion_minimal"] is False


def test_budget_exhaustion_preserves_partial_deletion_scan():
    data = SimpleNamespace(group=np.zeros(20, dtype=int))
    evaluator = FakeEvaluator({(1, 2): 12.0})
    values = iter([0.0, 0.0, 31.0, 31.0])
    result = iterative_prune(
        data,
        evaluator,
        initial_fit(),
        np.array([0, 1, 2]),
        0.1,
        np.array([0.0]),
        budget_s=30.0,
        clock=lambda: next(values),
        fitter=fit({}),
    )
    assert result["termination"] == "budget_exhausted_during_deletion_scan"
    assert result["iterations"][0]["deletions_evaluated"] == 1
    assert result["deletion_minimal"] is False
