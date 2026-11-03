from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest
from soft_solvers import _fisher_system, fit_soft
from test_timing_model import DenseJacobian, LinearPlan, synthetic_problem
from timing_model import TimingObjective


class FixedPosteriorGaussian:
    def __init__(self, measured, posterior=1.0, clock=None):
        self.measured = np.asarray(measured, dtype=float)
        self.posterior = posterior
        self.clock = clock
        self.calls = 0

    def evaluate(
        self,
        predicted,
        visible,
        *,
        sigma_hz,
        return_gradient,
        return_precision,
    ):
        self.calls += 1
        posterior = np.broadcast_to(self.posterior, predicted.shape).astype(float).copy()
        posterior *= visible
        residual = self.measured[:, None] - predicted
        if self.clock is not None and self.calls == 2:
            self.clock[0] = 5.1
        return {
            "total_log_likelihood": -0.5
            * float(np.sum(posterior * (residual / sigma_hz) ** 2)),
            "prediction_gradient": posterior * residual / sigma_hz**2,
            "row_association_probability": posterior,
        }


class EastOnlyPlan:
    def __init__(self, data, satellites):
        self.data = data
        self.satellites = np.asarray(satellites, dtype=int)

    def predict(self, parameters):
        rows = len(self.data.times)
        count = len(self.satellites)
        matrix = np.zeros((rows * count, len(parameters)))
        matrix[:, 0] = 1.0
        prediction = matrix @ parameters
        visible = np.ones(rows * count, dtype=bool)
        return prediction, visible, DenseJacobian(matrix)


class CrossingVisibilityPlan(EastOnlyPlan):
    def predict(self, parameters):
        prediction, visible, jacobian = super().predict(parameters)
        visible[:] = parameters[0] >= 0.0
        return prediction, visible, jacobian


def _east_problem(measured, *, likelihood=None):
    measured = np.asarray(measured, dtype=float)
    data = SimpleNamespace(
        times=np.linspace(149.0, 151.0, len(measured)),
        measured=measured.copy(),
        receiver=np.zeros(len(measured), dtype=int),
        numbers=np.array([100]),
        nodes=np.array([100.0, 200.0]),
        reference_time_s=150.0,
    )
    if likelihood is None:
        likelihood = FixedPosteriorGaussian(measured)
    return data, np.zeros(7), np.array([0]), likelihood


def test_fisher_improves_monotonically_and_returns_standard_fields():
    data, objective = synthetic_problem(2)
    data.measured = np.array([100.0, 150.0, -80.0, 40.0])
    likelihood = FixedPosteriorGaussian(data.measured)
    result = fit_soft(
        data,
        objective.initial_parameters,
        objective.satellites,
        likelihood,
        100.0,
        budget_s=5.0,
        max_iterations=20,
        plan_factory=LinearPlan,
    )
    assert result["is_em"] is False
    assert result["soft_likelihood"] is True
    assert result["objective"] < result["initial_objective"]
    assert result["observed_monotone"] is True
    assert np.all(np.diff(result["objective_trace"]) <= 1.0e-9)
    assert result["best_is_terminal"] is True
    assert result["success"] is result["stationarity_certified"]
    for key in (
        "parameters",
        "data_objective",
        "prior_objective",
        "global_shift_s",
        "individual_shifts_s",
        "total_shifts_s",
    ):
        assert key in result
    assert result["accepted_trace"]
    for row in result["accepted_trace"]:
        assert row["elapsed_s"] >= 0.0
        assert np.isfinite(row["objective"])
        assert np.isfinite(row["projected_gradient_inf_norm"])
        assert row["vector"].shape == result["vector"].shape


def test_fisher_enforces_bounds_and_can_certify_boundary_optimum():
    data, initial, satellites, likelihood = _east_problem([1000.0, 1000.0])
    result = fit_soft(
        data,
        initial,
        satellites,
        likelihood,
        1.0,
        budget_s=5.0,
        max_iterations=10,
        plan_factory=EastOnlyPlan,
    )
    assert result["vector"][0] == pytest.approx(200.0)
    assert result["projected_gradient_inf_norm"] == pytest.approx(0.0)
    assert result["stationarity_certified"] is True
    assert result["success"] is True


def test_fisher_uses_tiny_soft_posterior_without_clipping():
    data, objective = synthetic_problem(1)
    posterior = np.full((len(data.times), 1), 1.0e-12)
    likelihood = FixedPosteriorGaussian(np.zeros(len(data.times)), posterior)
    audited = TimingObjective(
        data,
        objective.initial_parameters,
        objective.satellites,
        likelihood,
        2.0,
        plan_factory=LinearPlan,
    )
    vector = audited.initial_vector
    audited.evaluate(vector)
    hessian, _visible = _fisher_system(audited, vector, audited.last)
    design = data.location_design[:, 0]
    expected = float(np.sum(posterior[:, 0] * design**2) / 4.0)
    assert hessian[0, 0] == pytest.approx(expected, rel=1.0e-12)
    assert hessian[0, 0] > 0.0


def test_visibility_crossing_prevents_false_branch_convergence():
    data, initial, satellites, likelihood = _east_problem([0.0, 0.0])
    result = fit_soft(
        data,
        initial,
        satellites,
        likelihood,
        1.0,
        budget_s=5.0,
        max_iterations=2,
        plan_factory=CrossingVisibilityPlan,
    )
    assert result["projected_gradient_inf_norm"] == pytest.approx(0.0)
    assert result["visibility_probe_stable"] is False
    assert result["stationarity_certified"] is False
    assert result["success"] is False
    assert "visibility" in result["stationarity_scope"]


def test_deadline_retains_improving_finite_candidate_as_nonterminal_best():
    now = [0.0]

    def clock():
        return now[0]

    likelihood = FixedPosteriorGaussian([10.0, 10.0], clock=now)
    data, initial, satellites, _unused = _east_problem(
        [10.0, 10.0],
        likelihood=likelihood,
    )
    result = fit_soft(
        data,
        initial,
        satellites,
        likelihood,
        1.0,
        budget_s=5.0,
        max_iterations=10,
        clock=clock,
        plan_factory=EastOnlyPlan,
    )
    assert result["deadline_reached"] is True
    assert result["objective"] < result["initial_objective"]
    assert result["best_is_terminal"] is False
    assert result["stationarity_certified"] is False
    assert result["success"] is False
    assert result["status"] == "limit_reached_best_finite_nonterminal"


def test_lbfgsb_success_alone_is_not_reported_as_convergence():
    data, initial, satellites, likelihood = _east_problem([10.0, 10.0])

    def no_move_minimizer(function, start, **_options):
        value, _gradient = function(start)
        return SimpleNamespace(
            x=np.asarray(start, dtype=float),
            fun=value,
            success=True,
            message="synthetic ftol",
        )

    result = fit_soft(
        data,
        initial,
        satellites,
        likelihood,
        1.0,
        budget_s=5.0,
        method="lbfgsb",
        minimizer=no_move_minimizer,
        plan_factory=EastOnlyPlan,
    )
    assert result["optimizer_reported_success"] is True
    assert result["projected_gradient_inf_norm"] > 1.0
    assert result["stationarity_certified"] is False
    assert result["success"] is False
    assert result["status"] == "optimizer_stopped_stationarity_unverified"


def test_budget_and_method_are_bounded():
    data, initial, satellites, likelihood = _east_problem([1.0])
    with pytest.raises(ValueError, match="90"):
        fit_soft(data, initial, satellites, likelihood, 1.0, budget_s=90.1)
    with pytest.raises(ValueError, match="method"):
        fit_soft(data, initial, satellites, likelihood, 1.0, method="em")
