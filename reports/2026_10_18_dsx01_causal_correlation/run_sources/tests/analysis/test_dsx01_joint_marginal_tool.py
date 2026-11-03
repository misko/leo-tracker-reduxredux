"""Dense numerical oracles for the joint-nuisance marginalization experiment."""

import importlib
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest


@pytest.fixture
def tool():
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
    try:
        yield importlib.import_module("dsx01_joint_marginal")
    finally:
        sys.path.pop(0)


def test_integrated_cost_and_coefficients_match_dense_covariance(tool):
    rng = np.random.default_rng(31)
    y, u, s = rng.normal(size=19), rng.normal(size=(19, 7)), np.linspace(0.7, 1.6, 19)
    result = tool.integrated_gaussian(y, u, s)
    cov = np.diag(s * s) + u @ u.T
    quadratic = y @ np.linalg.solve(cov, y)
    logvolume = np.linalg.slogdet(cov)[1] - np.log(s * s).sum()
    np.testing.assert_allclose(result["quadratic"], quadratic, rtol=1e-12)
    np.testing.assert_allclose(result["logvolume"], logvolume, rtol=1e-12)
    np.testing.assert_allclose(result["residual"] @ result["residual"], quadratic + logvolume)
    np.testing.assert_allclose(result["coefficient"], u.T @ np.linalg.solve(cov, y))


def test_volume_penalizes_uncertainty_even_when_residual_is_zero(tool):
    small = tool.integrated_gaussian(np.zeros(6), np.eye(6), 1)
    large = tool.integrated_gaussian(np.zeros(6), np.eye(6) * 10, 1)
    assert small["quadratic"] == large["quadratic"] == 0
    assert large["logvolume"] > small["logvolume"]


def test_relinearization_preserves_absolute_phase_prior(tool):
    h, absolute, reference = np.array([4.0, -3.0]), np.array([0.7, -0.2]), np.array([2.0, 1.0])
    intercept = np.array([12.0, 24.0])
    at_reference = intercept + h * reference
    corrected = tool.absolute_phase_linearization(at_reference, h, reference)
    np.testing.assert_allclose(corrected + h * absolute, intercept + h * absolute)
    np.testing.assert_allclose(corrected, intercept)


def test_coordinate_rotation_and_point_permutation_preserve_objective(tool):
    rng = np.random.default_rng(25)
    y, u = rng.normal(size=13), rng.normal(size=(13, 5))
    q, _ = np.linalg.qr(rng.normal(size=(5, 5)))
    p = rng.permutation(13)
    a, b = tool.integrated_gaussian(y, u, 2), tool.integrated_gaussian(y[p], u[p] @ q, 2)
    np.testing.assert_allclose(
        a["residual"] @ a["residual"], b["residual"] @ b["residual"], rtol=1e-13
    )
    np.testing.assert_allclose(a["conditional_residual_hz"][p], b["conditional_residual_hz"])


def test_student_bound_equals_exact_student_without_nuisance_modes(tool):
    robust = importlib.import_module("dsx01_robust_joint")
    y, g = np.array([2.0, -1.0, 3.0, 0.2, -0.4]), np.array([0, 0, 0, 1, 1])
    result = robust.student_joint_bound(y, np.empty((5, 0)), 1.0, g)
    expected = sum((4 + (g == k).sum()) * np.log1p(np.sum(y[g == k] ** 2) / 4) for k in range(2))
    np.testing.assert_allclose(result["residual"] @ result["residual"], expected, rtol=1e-12)


def test_student_variational_cost_bounds_numerically_integrated_evidence(tool):
    robust = importlib.import_module("dsx01_robust_joint")
    y, u = np.array([1.2, -0.4, 2.3]), np.array([[0.6], [-0.2], [0.3]])
    nodes, weights = np.polynomial.hermite.hermgauss(100)
    energy = np.sum((y[:, None] - u * (np.sqrt(2) * nodes)) ** 2, axis=0)
    density = np.dot(weights, (1 + energy / 4) ** (-3.5)) / np.sqrt(np.pi)
    exact = -2 * np.log(density)
    first = robust.student_joint_bound(y, u, 1.0, np.zeros(3, dtype=int), iterations=1)
    final = robust.student_joint_bound(y, u, 1.0, np.zeros(3, dtype=int))

    def cost(r):
        return r["residual"] @ r["residual"]

    assert cost(final) >= exact - 1e-10
    assert cost(final) <= cost(first) + 1e-10
    assert cost(final) - exact < 0.2


def test_report_decomposition_accounts_for_all_integrated_and_student_terms(tool):
    robust = importlib.import_module("dsx01_robust_joint")
    report = importlib.import_module("report_dsx01_joint_marginal")
    rng = np.random.default_rng(92)
    y, u = rng.normal(size=12), rng.normal(size=(12, 5))
    result = robust.student_joint_bound(y, u, 1.3, np.repeat([0, 1], 6))
    result["elevation"] = np.linspace(-3, 4, 12)
    problem = SimpleNamespace(sigma=1.3, slices=[slice(0, 6), slice(6, 12)])
    parts = report.objective_parts(problem, result)
    expected = result["residual"] @ result["residual"] + np.sum(
        (np.maximum(0, -result["elevation"]) / 2) ** 2
    )
    np.testing.assert_allclose(parts["total"], expected, rtol=1e-13)
