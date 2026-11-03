import numpy as np
import pytest

from leo.analysis.localization_linear import (
    solve_diagonal_nuisance,
    student_t_branch_quadratics,
)


def test_bulk_quadratics_match_original_branch_scatter():
    from leo.analysis.localization_soft import (
        _CompactBranch,
        _scatter_student_t_contribution,
    )

    rng = np.random.default_rng(919)
    n, m, q = 31, 9, 6
    residuals = rng.normal(size=(n, m)) * 3
    jacobians = rng.normal(size=(n, m, q))
    base = rng.normal(size=(m, m))
    covariance = base @ base.T + np.eye(m)
    probabilities = rng.uniform(size=n)
    probabilities /= probabilities.sum() * 1.2  # Nonzero background mass.
    probabilities[:2] = [0., 1e-200]
    matrices, gradients = student_t_branch_quadratics(
        residuals, jacobians, covariance, probabilities,
    )
    for i in range(n):
        expected_matrix, expected_gradient = np.zeros((q, q)), np.zeros(q)
        _scatter_student_t_contribution(
            expected_matrix, expected_gradient, np.arange(q),
            _CompactBranch(residuals[i], probabilities[i], np.zeros(m),
                           jacobians[i], np.arange(q), covariance), 4.,
        )
        np.testing.assert_allclose(matrices[i], expected_matrix, rtol=1e-12, atol=0.)
        np.testing.assert_allclose(gradients[i], expected_gradient, rtol=1e-12, atol=0.)
    assert np.count_nonzero(matrices[1]) > 0  # Tiny mass is not pruned.


def test_bulk_quadratic_gradient_matches_finite_difference_t_objective():
    from leo.analysis.robust_likelihood import student_t_logpdf

    r = np.array([[2., -1.], [3., .5]])
    j = np.array([[[1., 2.], [3., 1.]], [[-.5, 1.], [2., 3.]]])
    c = np.array([[2., .2], [.2, 1.]])
    p = np.array([.2, .7])
    _, gradients = student_t_branch_quadratics(r, j, c, p)
    for branch in range(2):
        for axis in range(2):
            delta = np.zeros(2)
            delta[axis] = 1e-5
            plus = p[branch] * student_t_logpdf(r[branch]-j[branch]@delta, c, 4.)
            minus = p[branch] * student_t_logpdf(r[branch]+j[branch]@delta, c, 4.)
            assert gradients[branch, axis] == pytest.approx((plus-minus)/2e-5, abs=1e-9)


def test_bulk_empty_and_invalid_responsibilities():
    matrices, gradients = student_t_branch_quadratics(
        np.empty((0, 2)), np.empty((0, 2, 6)), np.eye(2), np.empty(0),
    )
    assert matrices.shape == (0, 6, 6) and gradients.shape == (0, 6)
    with pytest.raises(ValueError):
        student_t_branch_quadratics(np.ones((2, 2)), np.ones((2, 2, 6)),
                                    np.eye(2), np.array([.7, .7]))


@pytest.mark.parametrize("n", [0, 1, 19, 800])
def test_matches_full_dense_system_and_residual(n):
    rng = np.random.default_rng(871)
    b = rng.normal(size=(5, n)) / max(1, np.sqrt(n))
    d = rng.uniform(0.5, 3, size=n)
    design = rng.normal(size=(8, 5))
    a = design.T @ design + np.eye(5) + (b / d) @ b.T
    rhs = rng.normal(size=5 + n)
    full = np.block([[a, b], [b.T, np.diag(d)]])
    expected = np.linalg.solve(full, rhs)
    actual = solve_diagonal_nuisance(a, b, d, rhs[:5], rhs[5:])
    np.testing.assert_allclose(actual, expected, rtol=1e-11, atol=1e-12)
    np.testing.assert_allclose(full @ actual, rhs, rtol=1e-11, atol=1e-12)


def test_weighted_branch_assembly_with_shared_satellite_and_damping():
    rng = np.random.default_rng(413)
    k, n = 5, 9
    full = np.diag(np.r_[np.ones(k) * .3, np.ones(n) * 4.])
    rhs = rng.normal(size=k+n)
    for satellite in [0, 0, 2, 4, 8, 8]:
        design = np.zeros((3, k+n))
        design[:, :k] = rng.normal(size=(3, k))
        design[:, k+satellite] = rng.normal(size=3)
        c = rng.normal(size=(3, 3))
        covariance = c @ c.T + np.eye(3)
        weight = rng.uniform(.01, .99)
        full += weight * design.T @ np.linalg.solve(covariance, design)
    full += np.diag(.02 * np.diag(full))
    actual = solve_diagonal_nuisance(full[:k, :k], full[:k, k:],
                                    np.diag(full[k:, k:]), rhs[:k], rhs[k:])
    np.testing.assert_allclose(actual, np.linalg.solve(full, rhs), rtol=1e-12, atol=1e-12)


@pytest.mark.parametrize("d", [0., -1., np.nan, np.inf])
def test_rejects_invalid_nuisance_precision(d):
    with pytest.raises(ValueError):
        solve_diagonal_nuisance(np.eye(2), np.ones((2, 1)), np.array([d]),
                                np.zeros(2), np.zeros(1))


def test_does_not_hide_unidentified_or_indefinite_shared_direction():
    for a in [np.diag([1., 0.]), np.diag([1., -1.])]:
        with pytest.raises(np.linalg.LinAlgError):
            solve_diagonal_nuisance(a, np.zeros((2, 1)), np.ones(1),
                                    np.ones(2), np.ones(1))


def test_invalid_shape_or_asymmetry_rejected():
    with pytest.raises(ValueError):
        solve_diagonal_nuisance(np.eye(2), np.zeros((2, 2)), np.ones(1),
                                np.ones(2), np.ones(1))
    with pytest.raises(ValueError):
        solve_diagonal_nuisance(np.array([[1., .1], [0., 1.]]), np.zeros((2, 1)),
                                np.ones(1), np.ones(2), np.ones(1))
