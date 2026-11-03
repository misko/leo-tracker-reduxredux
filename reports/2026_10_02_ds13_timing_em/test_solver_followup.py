from types import SimpleNamespace

import numpy as np
from finite_set_likelihood import prepare_finite_set_likelihood
from gated_likelihood import GatedLikelihood
from solver_followup import fit_block_observed, fit_gem
from test_timing_model import LinearPlan, synthetic_problem


def test_followup_gem_decreases_fixed_q_and_observed_objective():
    data, objective = synthetic_problem(1)
    data.measured = objective.likelihood.target[:, 0].copy()
    result = fit_gem(
        data,
        objective.initial_parameters,
        objective.satellites,
        objective.likelihood,
        objective.sigma_hz,
        budget_s=5.0,
        max_iterations=3,
        plan_factory=LinearPlan,
    )
    accepted = [
        row for row in result["fixed_posterior_q_history"]
        if row["accepted"] is not None
    ]
    assert accepted
    assert all(row["accepted"] < row["start"] for row in accepted)
    assert result["observed_monotone"] is True
    assert np.all(np.diff(result["observed_objective_history"]) <= 1e-9)


def test_followup_gem_step_stays_inside_exact_gate_support():
    data, _ = synthetic_problem(2)
    data.group = np.arange(len(data.times))
    data.measured = np.array([20.0, -30.0, 40.0, -50.0])
    prepared = prepare_finite_set_likelihood(data.measured, data.group)
    likelihood = GatedLikelihood(
        prepared,
        detection_probability=0.4,
        clutter_rate=2.0,
        gate_hz=300.0,
    )
    result = fit_gem(
        data,
        np.zeros(8),
        [0, 1],
        likelihood,
        100.0,
        budget_s=5.0,
        max_iterations=2,
        plan_factory=LinearPlan,
    )
    assert result["observed_monotone"] is True
    assert all(
        row["accepted"] is None or row["accepted"] < row["start"]
        for row in result["fixed_posterior_q_history"]
    )
    assert result["objective"] <= result["initial_objective"] + 1e-9


def test_followup_block_timeout_retains_best_finite_nonterminal():
    data, objective = synthetic_problem(2)
    now = [0.0]

    def clock():
        return now[0]

    def interrupted_minimizer(function, start, callback, **_options):
        start = np.asarray(start, dtype=float)
        initial_value, gradient = function(start)
        direction = -gradient / max(np.linalg.norm(gradient), 1.0)
        best_value = initial_value
        for fraction in 10.0 ** -np.arange(1, 10):
            candidate = start + fraction * direction
            value, _ = function(candidate)
            if value < best_value:
                best_value = value
                break
        assert best_value < initial_value
        now[0] = 5.1
        callback(start)
        return SimpleNamespace(x=start, success=False)

    result = fit_block_observed(
        data,
        objective.initial_parameters,
        objective.satellites,
        objective.likelihood,
        objective.sigma_hz,
        budget_s=5.0,
        minimizer=interrupted_minimizer,
        clock=clock,
        plan_factory=LinearPlan,
    )
    assert result["deadline_reached"] is True
    assert result["objective"] < result["initial_objective"]
    assert result["best_is_terminal"] is False
    assert result["success"] is False
    assert result["status"] == "limit_reached_best_finite_nonterminal"


def test_followup_block_history_is_monotone_and_returns_old_keys():
    data, objective = synthetic_problem(2)
    result = fit_block_observed(
        data,
        objective.initial_parameters,
        objective.satellites,
        objective.likelihood,
        objective.sigma_hz,
        budget_s=5.0,
        max_cycles=2,
        plan_factory=LinearPlan,
    )
    assert result["observed_monotone"] is True
    assert np.all(np.diff(result["observed_objective_history"]) <= 1e-9)
    for key in (
        "parameters",
        "global_shift_s",
        "individual_shifts_s",
        "total_shifts_s",
        "vector",
        "objective",
        "status",
        "success",
    ):
        assert key in result
