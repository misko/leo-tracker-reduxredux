from types import SimpleNamespace

import numpy as np
import pytest

from finite_set_likelihood import prepare_finite_set_likelihood
from gated_likelihood import GatedLikelihood
from solvers import FixedPosteriorQ, fit_block_observed, fit_direct, fit_gem
from test_timing_model import GaussianLikelihood, LinearPlan, synthetic_problem
from timing_model import TimingObjective


def test_timing_objective_integrates_with_parent_gated_likelihood():
    data, _ = synthetic_problem(2)
    data.group = np.arange(len(data.times))
    prepared = prepare_finite_set_likelihood(data.measured, data.group)
    likelihood = GatedLikelihood(
        prepared,
        detection_probability=0.4,
        clutter_rate=2.0,
        gate_hz=300.0,
    )
    objective = TimingObjective(
        data,
        np.zeros(8),
        [0, 1],
        likelihood,
        100.0,
        plan_factory=LinearPlan,
    )
    value, gradient = objective.evaluate(objective.initial_vector)
    assert np.isfinite(value)
    assert np.all(np.isfinite(gradient))
    assert objective.last["likelihood"]["row_association_probability"].shape == (4, 2)


def test_fixed_posterior_q_uses_duplicate_row_weights_and_can_improve():
    data, _ = synthetic_problem(1)
    data.measured = np.array([1.0, 3.0, 0.0, 0.0])
    posterior = np.array([[0.25], [0.75], [0.0], [0.0]])
    likelihood = GaussianLikelihood(np.array([[1.0], [3.0], [0.0], [0.0]]), posterior)
    objective = TimingObjective(
        data,
        np.zeros(7),
        [0],
        likelihood,
        1.0,
        plan_factory=LinearPlan,
    )
    start = objective.initial_vector
    objective.evaluate(start)
    q_objective = FixedPosteriorQ(objective, start, posterior)
    initial_q, _ = q_objective.evaluate(start)
    from scipy.optimize import minimize

    fitted = minimize(
        q_objective.evaluate,
        start,
        jac=True,
        method="L-BFGS-B",
        bounds=objective.bounds,
    )
    final_q, _ = q_objective.evaluate(fitted.x)
    assert initial_q == pytest.approx(0.5 * (0.25 * 1.0**2 + 0.75 * 3.0**2))
    assert final_q < initial_q


def test_fixed_posterior_q_freezes_alias_branch_and_hard_gate_support():
    data, _ = synthetic_problem(1)

    class VisibilityPlan(LinearPlan):
        def predict(self, parameters):
            predicted, visible, jacobian = super().predict(parameters)
            visible[:] = parameters[0] >= 0
            return predicted, visible, jacobian

    alias_hz = 1 / 4.4e-6
    data.measured = np.full(4, alias_hz + 10.0)
    posterior = np.ones((4, 1))
    likelihood = GaussianLikelihood(np.full((4, 1), 10.0), posterior)
    objective = TimingObjective(
        data,
        np.zeros(7),
        [0],
        likelihood,
        100.0,
        plan_factory=VisibilityPlan,
    )
    q_objective = FixedPosteriorQ(objective, objective.initial_vector, posterior)
    initial_q, _ = q_objective.evaluate(objective.initial_vector)
    assert initial_q == pytest.approx(0.5 * 4 * (10.0 / 100.0) ** 2)
    outside = objective.initial_vector
    outside[2] = 2000.0
    invalid_q, _ = q_objective.evaluate(outside)
    assert invalid_q >= 1e30
    changed_visibility = objective.initial_vector
    changed_visibility[0] = -1.0
    visibility_q, _ = q_objective.evaluate(changed_visibility)
    assert visibility_q >= 1e30


def test_gem_observed_objective_is_monotone_and_gauge_is_preserved():
    data, objective = synthetic_problem(2)
    result = fit_gem(
        data,
        objective.initial_parameters,
        objective.satellites,
        objective.likelihood,
        objective.sigma_hz,
        budget_s=3.0,
        max_iterations=4,
        plan_factory=LinearPlan,
    )
    history = result["observed_objective_history"]
    assert result["is_em"] is True
    assert result["observed_monotone"] is True
    assert result["stationarity_certified"] is False or result["success"] is True
    assert result["status"] != "converged"
    assert np.all(np.diff(history) <= 1e-9)
    assert np.sum(result["individual_shifts_s"]) == pytest.approx(0.0, abs=1e-12)
    np.testing.assert_allclose(
        result["parameters"][6 + result["satellite_indices"]],
        result["global_shift_s"] + result["individual_shifts_s"],
    )


def test_gate_blocked_gem_plateau_is_not_called_stationary():
    data, _ = synthetic_problem(1)
    data.group = np.arange(len(data.times))
    data.measured[:] = 5000.0
    prepared = prepare_finite_set_likelihood(data.measured, data.group)
    likelihood = GatedLikelihood(
        prepared,
        detection_probability=0.8,
        clutter_rate=2.0,
        gate_hz=300.0,
    )

    def stationary_minimizer(function, start, **_options):
        value, _gradient = function(start)
        return SimpleNamespace(x=np.asarray(start), fun=value, success=True, message="flat")

    result = fit_gem(
        data,
        np.zeros(7),
        [0],
        likelihood,
        100.0,
        budget_s=3.0,
        max_iterations=1,
        minimizer=stationary_minimizer,
        plan_factory=LinearPlan,
    )
    assert result["projected_gradient_inf_norm"] == pytest.approx(0.0)
    assert result["active_gate_interior"] is False
    assert result["stationarity_certified"] is False
    assert result["success"] is False
    assert result["status"] == "small_monotone_step_stationarity_unverified"


def test_direct_returns_full_parameters_and_positive_budget_receipt():
    data, objective = synthetic_problem(2)
    result = fit_direct(
        data,
        objective.initial_parameters,
        objective.satellites,
        objective.likelihood,
        objective.sigma_hz,
        budget_s=3.0,
        plan_factory=LinearPlan,
    )
    assert result["parameters"].shape == objective.initial_parameters.shape
    assert result["budget_s"] == 3.0
    assert result["elapsed_s"] <= result["budget_s"]
    assert result["method"] == "direct_bounded_lbfgsb"
    assert result["stationarity_certified"] is False
    np.testing.assert_array_equal(
        result["optimizer_scale"],
        [20.0, 20.0, 1000.0, 10.0, 1000.0, 10.0, 1.0, 1.0],
    )


def test_direct_reports_when_retained_best_is_not_optimizer_terminal():
    data, objective = synthetic_problem(1)

    def misleading_minimizer(function, start, **_options):
        best = start.copy()
        function(best)
        terminal = start.copy()
        terminal[2] = 20.0
        terminal_value, _ = function(terminal)
        return SimpleNamespace(
            x=terminal,
            fun=terminal_value,
            success=True,
            message="synthetic terminal",
        )

    result = fit_direct(
        data,
        objective.initial_parameters,
        objective.satellites,
        objective.likelihood,
        objective.sigma_hz,
        budget_s=3.0,
        minimizer=misleading_minimizer,
        plan_factory=LinearPlan,
    )
    assert result["status"] == "best_retained_nonterminal"
    assert result["best_is_terminal"] is False
    assert result["success"] is False


def test_budget_is_bounded_and_block_solver_is_explicitly_not_em():
    data, objective = synthetic_problem(2)
    with pytest.raises(ValueError, match="30"):
        fit_direct(
            data,
            objective.initial_parameters,
            objective.satellites,
            objective.likelihood,
            objective.sigma_hz,
            budget_s=30.1,
            plan_factory=LinearPlan,
        )
    result = fit_block_observed(
        data,
        objective.initial_parameters,
        objective.satellites,
        objective.likelihood,
        objective.sigma_hz,
        budget_s=3.0,
        max_cycles=2,
        plan_factory=LinearPlan,
    )
    assert result["is_em"] is False
    assert result["method"].endswith("not_em")
    assert result["observed_monotone"] is True
    assert result["stationarity_certified"] is False
    assert result["status"] != "converged"


def test_direct_deadline_retains_best_valid_evaluation():
    data, objective = synthetic_problem(1)
    now = [0.0]

    def clock():
        return now[0]

    def slow_minimizer(function, start, callback, **_options):
        function(start)
        now[0] = 3.1
        callback(start)

    result = fit_direct(
        data,
        objective.initial_parameters,
        objective.satellites,
        objective.likelihood,
        objective.sigma_hz,
        budget_s=3.0,
        minimizer=slow_minimizer,
        clock=clock,
        plan_factory=LinearPlan,
    )
    assert result["status"] == "limit_reached"
    assert result["deadline_reached"] is True
    assert result["best_is_terminal"] is False
