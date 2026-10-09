"""Synthetic coupled active-face quadratics; no recording or position fitting."""

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest
import reduced_newton as solver

UPSTREAM = Path(__file__).resolve().parent.parent / "2026_10_09_position_error_iter99"
sys.path.insert(0, str(UPSTREAM))
SPEC = importlib.util.spec_from_file_location(
    "synthetic_face99", UPSTREAM / "test_tangent_polish.py"
)
helper = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(helper)


class Anisotropic:
    def __init__(self, eigenvalues=(1.0, 1000.0)):
        self.scales = np.ones(3)
        self.lower, self.upper = np.full(3, -np.inf), np.full(3, np.inf)
        self.normals = np.ones((1, 3))
        self.limits = np.zeros(1)
        _, _, vt = np.linalg.svd(self.normals, full_matrices=True)
        self.basis = vt[1:].T
        rotation = np.array([[0.8, -0.6], [0.6, 0.8]])
        self.hessian = rotation @ np.diag(eigenvalues) @ rotation.T
        self.target = np.array([0.2, -0.3])

    def evaluate(self, vector):
        residual = self.basis.T @ vector - self.target
        return (
            40000.0 + 1200.0 * sum(vector) + 0.5 * residual @ self.hessian @ residual,
            1200.0 * np.ones(3) + self.basis @ self.hessian @ residual,
            None,
        )


@pytest.fixture(autouse=True)
def fake_problem(monkeypatch):
    monkeypatch.setattr(solver, "_Problem", helper.Problem)


def test_anisotropic_coupled_face_qualifies_in_one_newton_round():
    objective = Anisotropic()
    result = solver.polish(objective, np.zeros(3))
    assert result["converged"] and result["rounds"] == 1
    assert result["evaluations"] == 8  # Initial + four central probes + three dampings.
    np.testing.assert_allclose(result["vector"], objective.basis @ objective.target, atol=1e-7)
    assert result["stationarity"] <= 0.001
    assert result["objective"] <= result["objective_ceiling"]
    assert all(row["feasible"] for row in result["trials"])
    eigenvalues = result["curvature_audits"][0]["eigenvalues"]
    np.testing.assert_allclose(eigenvalues, [1.0, 1000.0], atol=1e-7)


@pytest.mark.parametrize("eigenvalues", [(-1.0, 1000.0), (0.0, 1000.0)])
def test_no_ridge_for_indefinite_or_unidentified_modes(eigenvalues):
    result = solver.polish(Anisotropic(eigenvalues), np.zeros(3))
    assert not result["converged"]
    assert result["rounds"] == 0
    assert result["stop_reason"] == "reduced-hessian-not-positive-definite"


def test_hessian_sweep_budget_reserved_and_final_cap():
    result = solver.polish(Anisotropic(), np.zeros(3), maximum_evaluations=5)
    assert result["evaluations"] == 1
    assert result["stop_reason"] == "insufficient-budget-for-curvature"
    result = solver.polish(Anisotropic(), np.zeros(3), maximum_evaluations=6)
    assert result["evaluations"] <= 6 and result["converged"]


def test_active_face_with_no_free_tangent_cannot_fake_kkt():
    objective = Anisotropic()
    objective.normals = np.eye(3)
    objective.limits = np.zeros(3)
    # Override objective with a feasible interior-descent optimum to make active
    # normal multipliers invalid, while the active-face nullspace is empty.
    objective.evaluate = lambda vector: (40000.0 - sum(vector), -np.ones(3), None)
    result = solver.polish(objective, np.zeros(3))
    assert not result["converged"]
    assert result["stop_reason"] == "empty-active-face"


def test_fixed_lock_scales_and_infeasible_seed():
    objective = Anisotropic()
    objective.scales = np.array([2.0, 5.0, 7.0])
    result = solver.polish(objective, np.zeros(3))
    assert result["converged"]
    np.testing.assert_allclose(result["vector"], objective.basis @ objective.target, atol=1e-7)
    with pytest.raises(ValueError):
        solver.polish(objective, -np.ones(3))
