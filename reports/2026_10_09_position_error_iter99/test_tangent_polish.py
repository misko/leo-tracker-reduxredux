"""Synthetic constrained quadratics; no recording or position optimizer."""

import numpy as np
import pytest
import tangent_polish as solver
from scipy.optimize import nnls


class Problem:
    def __init__(self, objective, start, **options):
        self.objective = objective
        self.start = start.copy()
        self.scales = np.asarray(objective.scales)
        self.lower, self.upper = objective.lower.copy(), objective.upper.copy()
        self.free = np.flatnonzero(self.lower != self.upper)

    def constraints(self, vector):
        return self.objective.normals @ vector - self.objective.limits

    def jacobian(self, vector):
        return self.objective.normals

    def feasible(self, vector):
        return bool(
            np.all(self.constraints(vector) >= -1e-7)
            and np.all(vector >= self.lower - 1e-9)
            and np.all(vector <= self.upper + 1e-9)
        )

    def stationarity(self, vector, gradient):
        g = (gradient * self.scales)[self.free]
        rows = list(
            (self.jacobian(vector) * self.scales)[:, self.free][self.constraints(vector) <= 1e-6]
        )
        for i, j in enumerate(self.free):
            unit = np.eye(len(self.free))[i]
            if vector[j] / self.scales[j] <= self.lower[j] / self.scales[j] + 1e-7:
                rows.append(unit)
            if vector[j] / self.scales[j] >= self.upper[j] / self.scales[j] - 1e-7:
                rows.append(-unit)
        if rows:
            matrix = np.asarray(rows).T
            multipliers, _ = nnls(matrix, g)
            g -= matrix @ multipliers
        return float(np.max(abs(g), initial=0))


class Quadratic:
    def __init__(self, *, multiplier=1200.0, target=0.2, curvature=100.0, duplicate=False):
        self.scales = np.ones(2)
        self.lower = np.full(2, -np.inf)
        self.upper = np.full(2, np.inf)
        self.normals = np.array([[1.0, 1.0]])
        self.limits = np.zeros(1)
        if duplicate:
            self.normals = np.vstack([self.normals, 2 * self.normals])
            self.limits = np.zeros(2)
        self.multiplier, self.target, self.curvature = multiplier, target, curvature

    def evaluate(self, vector):
        tangent = np.array([1.0, -1.0]) / np.sqrt(2)
        residual = vector @ tangent - self.target
        value = 40000.0 + self.multiplier * sum(vector) + 0.5 * self.curvature * residual**2
        gradient = self.multiplier * np.ones(2) + self.curvature * residual * tangent
        return value, gradient, None


@pytest.fixture(autouse=True)
def problem(monkeypatch):
    monkeypatch.setattr(solver, "_Problem", Problem)


def test_coupled_face_succeeds_where_coordinate_newton_is_infeasible():
    objective = Quadratic()
    start = np.zeros(2)
    gradient = objective.evaluate(start)[1]
    raw_coordinate_newton = start.copy()
    raw_coordinate_newton[0] -= gradient[0] / 50
    assert not Problem(objective, start).feasible(raw_coordinate_newton)
    result = solver.polish(objective, start)
    assert result["converged"] and result["stationarity"] <= 0.001
    assert result["evaluations"] <= 100
    np.testing.assert_allclose(result["vector"], [0.2 / np.sqrt(2), -0.2 / np.sqrt(2)], atol=1e-8)
    for row in result["trials"]:
        assert row["feasible"]
        np.testing.assert_allclose(sum(row["vector"]), 0, atol=1e-12)
    assert result["objective"] <= result["objective_ceiling"]


def test_duplicate_normals_rank_and_receiver_exchange():
    objective = Quadratic(duplicate=True)
    result = solver.polish(objective, np.zeros(2))
    assert result["accepted"][0]["active_rank"] == 1
    other = solver.polish(Quadratic(target=-0.2), np.zeros(2))
    np.testing.assert_allclose(other["vector"], result["vector"][::-1], atol=1e-10)


def test_wrongly_active_face_does_not_fake_full_kkt_success():
    objective = Quadratic(multiplier=-1200.0, target=0)
    result = solver.polish(objective, np.zeros(2))
    assert not result["converged"]
    assert result["stationarity"] > 100
    assert result["rounds"] == 0


def test_lock_excluded_and_seed_not_projected():
    objective = Quadratic()
    objective.lower[0] = objective.upper[0] = 0
    result = solver.polish(objective, np.zeros(2))
    assert result["vector"][0] == 0
    np.testing.assert_array_equal(result["initial_vector"], np.zeros(2))


def test_nonpositive_curvature_refused():
    result = solver.polish(Quadratic(curvature=-100), np.zeros(2))
    assert not result["converged"]
    assert result["stop_reason"] == "nonpositive-or-nonfinite-curvature"


def test_budget_and_infeasible_start():
    result = solver.polish(Quadratic(), np.zeros(2), maximum_evaluations=1)
    assert result["evaluations"] == 1 and result["stop_reason"] == "evaluation-budget"
    with pytest.raises(ValueError):
        solver.polish(Quadratic(), np.array([-1.0, -1.0]))
    for invalid in (0, 101, True, 1.5):
        with pytest.raises(ValueError):
            solver.polish(Quadratic(), np.zeros(2), maximum_evaluations=invalid)
