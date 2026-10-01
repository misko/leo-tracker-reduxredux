import numpy as np
import pytest
from structured_curvature import solve_curvature


def test_free_position_and_regularized_nuisances_match_dense_solve():
    rng=np.random.default_rng(831)
    rows=rng.normal(size=(13,29));precision=np.r_[0.,0.,np.exp(rng.normal(size=27))]
    gradient=rng.normal(size=29)
    expected=np.linalg.solve(np.diag(precision)+rows.T@rows,gradient)
    actual=solve_curvature(precision,rows,gradient)
    np.testing.assert_allclose(actual,expected,atol=1e-10,rtol=1e-10)
    assert gradient@actual>0


def test_unidentified_position_is_not_silently_regularized():
    with pytest.raises(np.linalg.LinAlgError):
        solve_curvature(np.array([0.,0.,1.]),np.zeros((2,3)),np.ones(3))


def test_invalid_nuisance_prior_is_rejected():
    with pytest.raises(ValueError):
        solve_curvature(np.array([0.,0.,0.]),np.eye(3),np.ones(3))
