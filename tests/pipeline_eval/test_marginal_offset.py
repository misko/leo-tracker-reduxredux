"""Verify native Hertz scale, exact Gaussian elimination, and fixed held aliases."""

import numpy as np
import pytest
from scipy.linalg import solve_triangular

from tools.pipeline_eval.variants import marginal_offset as offset
from tools.pipeline_eval.variants import robust_em as lean


@pytest.mark.parametrize("sigma", [0.0, offset.SIGMA_HZ])
def test_rank_one_operator_matches_dense_covariance_and_explicit_offset_column(sigma):
    t = np.array([0, 0.5, 1.0, 2.4, 5.0, 8.6, 15.0, 25.0])
    cov = (150**2) * np.eye(len(t)) + (200**2) * np.exp(-abs(t[:, None] - t) / 4)
    one = np.ones(len(t))
    base = solve_triangular(np.linalg.cholesky(cov), np.eye(len(t)), lower=True)
    operator = offset.ConstantPrior(base, len(t), sigma)
    columns = np.column_stack((one, t - t.mean(), np.sin(t), 390 + 470 * np.sin(t / 4)))
    eliminated = operator @ columns
    augmented = cov + sigma**2 * np.outer(one, one)
    expected = columns.T @ np.linalg.solve(augmented, columns)
    assert np.allclose(eliminated.T @ eliminated, expected, rtol=1e-12, atol=1e-13)
    assert np.isclose(
        operator.log_volume, np.linalg.slogdet(augmented)[1] - np.linalg.slogdet(cov)[1]
    )
    if sigma:
        y = columns[:, -1]
        joint_matrix = np.r_[base @ one, 1 / sigma][:, None]
        joint_rhs = np.r_[base @ y, 0.0]
        coefficient = np.linalg.lstsq(joint_matrix, joint_rhs, rcond=None)[0][0]
        assert np.isclose(operator.posterior(y), coefficient)
        assert np.isclose(
            np.linalg.norm(operator @ y) ** 2,
            np.linalg.norm(joint_rhs - joint_matrix[:, 0] * coefficient) ** 2,
        )


def test_held_likelihood_integrates_prior_on_the_supplied_integer_branch():
    t = np.array([0.1, 2, 6, 8, 20.0])
    baseline = np.full(len(t), 600.0)
    track = lean.Track(t, baseline, 11.5e9, 0, True, t / 100, np.eye(len(t)) / 150)
    arc = lean.Arc(
        track,
        np.array([0]),
        (baseline + lean.PERIOD)[None],
        np.zeros((1, len(t), 2)),
        np.zeros((1, len(t))),
        np.zeros(1),
        np.zeros(1),
    )
    state = lean.State(np.zeros(2), np.zeros(4), np.zeros(4), np.zeros(1), 0.0)
    correct = lean.Assignment(arc, 0, 1, 0, 1)
    wrong = lean.Assignment(arc, 0, 0, 0, 1)
    a = offset.held_score([correct], state, offset.SIGMA_HZ)
    b = offset.held_score([wrong], state, offset.SIGMA_HZ)
    expected = 600**2 / (150**2 + len(t) * offset.SIGMA_HZ**2)
    expected += np.log1p(len(t) * offset.SIGMA_HZ**2 / 150**2) / len(t)
    assert np.isclose(a["held_normalized_mean_loss"], expected)
    assert a["held_raw_rms_hz"] == pytest.approx(600)
    assert a["held_orbits"] == 1 and b["held_orbits"] == 0
    assert b["held_raw_rms_hz"] > lean.PERIOD
