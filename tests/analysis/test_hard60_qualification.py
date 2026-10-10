"""Bounded calibration polishing must obey the original constrained KKT gate."""

from types import SimpleNamespace

import numpy as np
import pytest
from scipy.optimize import nnls

from leo.analysis import hard60_qualification, hard60_reduced_newton


class Quadratic:
    def __init__(self, curvature=100.0):
        self.scales = np.ones(2)
        self.lower = np.full(2, -np.inf)
        self.upper = np.full(2, np.inf)
        self.normals = np.array([[1.0, 1.0]])
        self.curvature = curvature

    def evaluate(self, vector):
        tangent = np.array([1.0, -1.0]) / np.sqrt(2)
        residual = vector @ tangent - 0.2
        return (
            40000.0 + 1200.0 * sum(vector) + 0.5 * self.curvature * residual**2,
            1200.0 * np.ones(2) + self.curvature * residual * tangent,
            None,
        )


class Problem:
    def __init__(self, objective, start, **options):
        self.objective = objective
        self.start = np.asarray(start).copy()
        self.scales = objective.scales
        self.lower, self.upper = objective.lower.copy(), objective.upper.copy()
        self.free = np.flatnonzero(self.lower != self.upper)

    def constraints(self, vector):
        return self.objective.normals @ vector

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
        normals = list(
            (self.jacobian(vector) * self.scales)[:, self.free][self.constraints(vector) <= 1e-6]
        )
        if normals:
            matrix = np.asarray(normals).T
            multipliers, _ = nnls(matrix, g)
            g -= matrix @ multipliers
        return float(np.max(abs(g), initial=0))


@pytest.fixture(autouse=True)
def fake_problem(monkeypatch):
    monkeypatch.setattr(hard60_reduced_newton, "_Problem", Problem)


@pytest.mark.parametrize("stage", ["calibration-prefit", "calibration-postfit"])
def test_polish_qualifies_coupled_active_face_under_score_ceiling(stage):
    objective = Quadratic()
    seed = np.zeros(2)
    result = hard60_qualification.qualify(
        objective,
        seed,
        objective.evaluate(seed)[0],
        retained=True,
        stage=stage,
        independently_qualified=False,
    )
    assert result["qualified"]
    assert result["objective_verified"]
    assert result["fit"]["objective"] <= result["fit"]["objective_ceiling"]
    assert result["fit"]["evaluations"] <= 100
    np.testing.assert_allclose(result["fit"]["vector"], [0.2 / np.sqrt(2), -0.2 / np.sqrt(2)])


def test_polish_refuses_nonpositive_curvature_and_wrong_saved_score():
    seed = np.zeros(2)
    objective = Quadratic(curvature=-100)
    result = hard60_qualification.qualify(
        objective,
        seed,
        objective.evaluate(seed)[0],
        retained=True,
        stage="calibration-postfit",
        independently_qualified=False,
    )
    assert not result["qualified"]
    assert result["fit"]["stop_reason"] == "reduced-hessian-not-positive-definite"
    result = hard60_qualification.qualify(
        Quadratic(),
        seed,
        -99,
        retained=True,
        stage="calibration-prefit",
        independently_qualified=False,
    )
    assert not result["qualified"] and result["objective_evaluations"] == 1


def test_only_failed_retained_calibration_uses_budget():
    result = hard60_qualification.qualify(
        object(),
        np.zeros(2),
        0,
        retained=False,
        stage="calibration-prefit",
        independently_qualified=False,
    )
    assert result["status"] == "not-triggered" and result["objective_evaluations"] == 0


def test_fixed_fit_validation_checks_point_score_and_stationarity(monkeypatch):
    monkeypatch.setattr(hard60_qualification, "_Problem", Problem)
    objective = Quadratic()
    objective.evaluate = lambda vector: (
        1.0,
        np.zeros(2),
        SimpleNamespace(responsibilities=np.ones(2), residual_hz=np.array([2.0, -2.0])),
    )
    saved = dict(vector=[0.0, 0.0], objective=1.0, converged=True, evaluations=1)
    qualified = hard60_qualification.validate_fixed_calibration_fit(objective, saved, np.zeros(2))
    assert qualified.converged and qualified.posterior_rms_hz == 2
    with pytest.raises(ValueError, match="retained point"):
        hard60_qualification.validate_fixed_calibration_fit(objective, saved, np.ones(2))
    with pytest.raises(ValueError, match="objective differs"):
        hard60_qualification.validate_fixed_calibration_fit(
            objective, {**saved, "objective": 0.0}, np.zeros(2)
        )
    with pytest.raises(ValueError, match="independent qualification"):
        hard60_qualification.validate_fixed_calibration_fit(
            objective, {**saved, "converged": False}, np.zeros(2)
        )
