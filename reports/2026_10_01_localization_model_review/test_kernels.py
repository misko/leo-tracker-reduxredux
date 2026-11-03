"""Independent dense oracles and evidence-preservation counterexamples."""
import numpy as np
import pytest

from kernels import collapsed_white_logpdf, shared_shift_logpdf


def dense_logpdf(y, covariance):
    sign, logdet = np.linalg.slogdet(covariance)
    assert sign == 1
    return -.5 * (y @ np.linalg.solve(covariance, y) + logdet
                  + len(y) * np.log(2 * np.pi))


@pytest.mark.parametrize("size", [1, 3, 40])
@pytest.mark.parametrize("clock_variance", [0., 1., 100.])
def test_shared_shift_matches_dense(size, clock_variance):
    y = np.random.default_rng(size).normal(size=size)
    covariance = .25 * np.eye(size) + clock_variance * np.ones((size, size))
    assert shared_shift_logpdf(y, .25, clock_variance) == pytest.approx(
        dense_logpdf(y, covariance), rel=1e-11, abs=1e-10)


@pytest.mark.parametrize("rows,columns", [(7, 0), (7, 2), (7, 12), (80, 12)])
def test_collapse_matches_dense_including_rank_deficiency(rows, columns):
    rng = np.random.default_rng(rows + columns)
    u, y = rng.normal(size=(rows, columns)), rng.normal(size=rows)
    if columns > 1:
        u[:, -1] = u[:, 0]
    assert collapsed_white_logpdf(y, u) == pytest.approx(
        dense_logpdf(y, np.eye(rows) + u @ u.T), rel=1e-12, abs=1e-10)


def test_inactive_nuisances_integrate_to_one():
    rng = np.random.default_rng(23)
    u, y = rng.normal(size=(12, 3)), rng.normal(size=12)
    assert collapsed_white_logpdf(y, np.column_stack((u, np.zeros((12, 6))))) == pytest.approx(
        collapsed_white_logpdf(y, u), abs=1e-12)


def test_shared_error_cannot_be_replaced_with_independent_track_noise():
    u = np.ones((2, 1)) * 3
    same, opposite = np.array([3., 3.]), np.array([3., -3.])
    independent = np.eye(2) * 10
    assert dense_logpdf(same, independent) == dense_logpdf(opposite, independent)
    assert collapsed_white_logpdf(same, u) > collapsed_white_logpdf(opposite, u) + 8


def test_determinant_prevents_rewarding_unnecessary_flexibility():
    # Both models have zero profiled residual/prior penalty, but different evidence.
    y = np.zeros(4)
    assert collapsed_white_logpdf(y, np.zeros((4, 1))) > collapsed_white_logpdf(
        y, np.ones((4, 1)) * 10)


@pytest.mark.parametrize("call", [
    lambda: shared_shift_logpdf([], 1, 1),
    lambda: shared_shift_logpdf([0], 0, 1),
    lambda: shared_shift_logpdf([0], 1, -1),
    lambda: collapsed_white_logpdf([0], np.ones((2, 1))),
    lambda: collapsed_white_logpdf([np.nan], np.ones((1, 1))),
])
def test_invalid_input(call):
    with pytest.raises(ValueError):
        call()
