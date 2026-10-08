"""Physical-equivalence, boundary and result-selection checks for Hard60 recovery."""

from types import SimpleNamespace

import numpy as np
import pytest
from scipy.optimize import OptimizeResult

from leo.analysis import hard60_bounded_fit as bounded
from leo.analysis.hard60_bounded_fit import _parameterization, _Problem, fit_bounded_position
from leo.analysis.regional_position_score import zero_sum_basis


class Quadratic:
    size = 10
    basis = zero_sum_basis(3)
    bank = SimpleNamespace(numbers=np.arange(3), nodes_s=np.array([-21.0, 31.0]))
    observations = SimpleNamespace(times_s=np.array([0.0, 10.0]))
    prior = SimpleNamespace(radius_km=250.0)
    target_shifts = np.array([25.0, -3.0, -2.0])
    target_rf = np.array([100.0, 90.0, -100.0, -90.0, 25.0])
    rf_scale = np.array([200.0, 2.0, 200.0, 2.0, 200.0])

    def evaluate(self, v):
        shifts = v[7] + self.basis @ v[8:]
        assert np.max(abs(shifts)) <= 21.00000001, "orbit bank extrapolation"
        residual = shifts - self.target_shifts
        rf = (v[2:7] - self.target_rf) / self.rf_scale
        value = 0.5 * (residual @ residual + rf @ rf)
        gradient = np.zeros(self.size)
        gradient[2:7] = rf / self.rf_scale
        gradient[7], gradient[8:] = residual.sum(), self.basis.T @ residual
        terms = SimpleNamespace(responsibilities=np.ones((1, 3)), residual_hz=residual[None])
        return float(value), gradient, terms


def vector_for_shifts(objective, shifts):
    v = np.zeros(objective.size)
    v[7], v[8:] = np.mean(shifts), objective.basis.T @ shifts
    return v


def test_box_parameterization_is_same_objective_and_priors():
    objective = Quadratic()
    seed = vector_for_shifts(objective, [19.0, -3.0, -2.0])
    p = _Problem(objective, seed, fixed_position=True)
    z, _, _, matrix, constant = _parameterization(p)
    np.testing.assert_allclose(matrix @ z + constant, seed, atol=1e-13)
    _, gradient, _ = objective.evaluate(seed)
    for i in range(len(z)):
        delta = np.eye(len(z))[i] * 1e-5
        numeric = (
            objective.evaluate(matrix @ (z + delta) + constant)[0]
            - objective.evaluate(matrix @ (z - delta) + constant)[0]
        ) / 2e-5
        np.testing.assert_allclose(numeric, (matrix.T @ gradient)[i], atol=1e-7)


@pytest.mark.parametrize("arm", ["fitted-c", "zero-c"])
def test_known_constrained_optimum_and_rf_ablation(arm):
    objective = Quadratic()
    seed = np.zeros(10)
    seed[:2] = [3.0, -5.0]
    answer, diagnostics = fit_bounded_position(
        objective,
        seed,
        rf_arm=arm,
        fixed_position=True,
        maximum_seconds=10,
        maximum_iterations=600,
    )
    assert answer.converged, answer.stationarity
    np.testing.assert_allclose(answer.vector[:2], seed[:2], atol=0)
    np.testing.assert_allclose(
        answer.vector[7] + objective.basis @ answer.vector[8:], [20.0, -3.0, -2.0], atol=1e-4
    )
    np.testing.assert_allclose(answer.vector[[3, 5]], [60.0, -60.0], atol=1e-4)
    assert max(abs(answer.vector[[3, 5]])) <= 60.00000001
    if arm == "zero-c":
        assert answer.vector[6] == 0
    assert diagnostics["terminal"] is not None
    assert answer.stop_reason == "independent-converged"


def test_expired_budget_cannot_be_success():
    with pytest.raises(TimeoutError):
        fit_bounded_position(Quadratic(), np.zeros(10), maximum_seconds=1e-12)


def test_success_and_best_feasible_keep_their_own_vectors(monkeypatch):
    class TwoWells(Quadratic):
        def evaluate(self, v):
            x = v[2] / 200
            value = (x * x - 1) ** 2 + 0.3 * (x * x * x / 3 - x)
            gradient = np.zeros(self.size)
            gradient[2] = (x * x - 1) * (4 * x + 0.3) / 200
            terms = SimpleNamespace(responsibilities=np.ones((1, 1)), residual_hz=np.ones((1, 1)))
            return value, gradient, terms

    def fake_minimize(fun, z, **kwargs):
        fun(z)
        trial = z.copy()
        trial[0] = 0.9
        fun(trial)
        return OptimizeResult(x=z, success=True, status=0, nit=1)

    monkeypatch.setattr(bounded, "minimize", fake_minimize)
    seed = np.zeros(10)
    seed[2] = -200
    answer, diagnostics = fit_bounded_position(TwoWells(), seed, fixed_position=True)
    assert answer.converged
    assert answer.vector[2] == -200
    assert diagnostics["best_feasible"].vector[2] == 180
    assert not diagnostics["best_feasible"].converged
    assert diagnostics["best_feasible"].objective < answer.objective
    assert diagnostics["terminal"].converged


def test_solver_success_cannot_override_failed_independent_audit(monkeypatch):
    def fake_minimize(fun, z, **kwargs):
        fun(z)
        return OptimizeResult(x=z, success=True, status=0, nit=1)

    monkeypatch.setattr(bounded, "minimize", fake_minimize)
    answer, diagnostics = fit_bounded_position(Quadratic(), np.zeros(10), fixed_position=True)
    assert diagnostics["solver_success"]
    assert not answer.converged
    assert answer.stop_reason == "nonstationary-solver-status-0"
