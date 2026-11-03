import time

import numpy as np
import pytest

from leo.analysis.localization_batched import fit_batched_soft
from leo.analysis.localization_soft import fit_joint_soft
from leo.analysis.robust_likelihood import student_t_logpdf


class Port:
    candidate_count = 3
    priors_piecewise_constant = True

    def __init__(self, seed):
        rng = np.random.default_rng(seed)
        self.observation_ids = (str(seed),)
        self.observation = rng.normal(size=8)
        self.jacobians = rng.normal(size=(3, 8, 6))
        self.columns = np.column_stack((np.tile(np.arange(5), (3, 1)), 5+np.arange(3)))
        self.covariance = np.eye(8)

    def linearize_candidates(self, state, indices):
        j, c = self.jacobians[indices], self.columns[indices]
        return dict(indices=indices, means=np.einsum('nmi,ni->nm', j, state[c]),
                    jacobians=j, columns=c, covariance=self.covariance,
                    eligible=np.ones(len(indices), dtype=bool))

    def score_all(self, state):
        means = self.linearize_candidates(state, np.arange(3))['means']
        return np.r_[[student_t_logpdf(self.observation-m, self.covariance, 4.)
                      - np.log(3) for m in means], -25.]


@pytest.mark.parametrize('iterations', [1, 8, 24])
def test_batched_matches_frozen_full_soft_trajectory(iterations):
    ports = [Port(82), Port(93)]
    initial = np.linspace(-.1, .2, 8)
    precision = np.r_[0., 0., 1., np.ones(5)*4]
    old = fit_joint_soft(initial, ports, precision, lambda x: np.linalg.norm(x[:2]) < 250,
                         max_iterations=iterations)
    new = fit_batched_soft(initial, ports, precision, lambda x: np.linalg.norm(x[:2]) < 250,
                           max_iterations=iterations)
    np.testing.assert_allclose(new.mean, old.mean, atol=2e-10, rtol=2e-9)
    np.testing.assert_allclose(new.objectives, old.objectives, atol=1e-10)
    assert new.reason == old.reason
    assert new.converged == old.converged
    for actual, expected in zip(new.responsibilities, old.responsibilities, strict=True):
        np.testing.assert_allclose(actual, expected, atol=1e-10)


def test_expired_deadline_does_not_report_stale_responsibilities():
    result = fit_batched_soft(np.zeros(8), [Port(1)], np.ones(8), lambda x: True,
                              deadline=time.monotonic()-1)
    assert result.reason == 'wall_budget' and not result.converged
    assert result.responsibilities is None and not result.responsibilities_at_mean


def test_duplicate_observations_and_missing_epoch_prior_rejected():
    with pytest.raises(ValueError):
        fit_batched_soft(np.zeros(8), [Port(1), Port(1)], np.ones(8), lambda x: True)
    with pytest.raises(ValueError):
        fit_batched_soft(np.zeros(8), [Port(1)], np.zeros(8), lambda x: True)


def test_fixed_position_profiles_nuisance_and_preserves_position_exactly():
    initial = np.linspace(-.3, .2, 8)
    result = fit_batched_soft(initial, [Port(82), Port(93)], np.ones(8), lambda x: True,
                              max_iterations=40, fixed_position=True)
    np.testing.assert_array_equal(result.mean[:2], initial[:2])
    assert result.objectives[-1] < result.objectives[0]
    assert np.linalg.norm(result.mean[2:]-initial[2:]) > .01
    assert result.converged


def test_fixed_position_one_step_matches_dense_restricted_system():
    from leo.analysis.localization_linear import student_t_branch_quadratics

    initial = np.zeros(8)
    port = Port(82)
    scores = port.score_all(initial)
    weights = np.exp(scores-scores.max())
    weights /= weights.sum()
    batch = port.linearize_candidates(initial, np.arange(3))
    matrices, gradients = student_t_branch_quadratics(
        port.observation-batch['means'], batch['jacobians'], batch['covariance'], weights[:-1],
    )
    full, rhs = np.eye(8), np.zeros(8)
    for matrix, gradient, columns in zip(matrices, gradients, batch['columns'], strict=True):
        full[np.ix_(columns, columns)] += matrix
        rhs[columns] += gradient
    step = np.r_[0., 0., np.linalg.solve(full[2:, 2:], rhs[2:])]
    actual = fit_batched_soft(initial, [port], np.ones(8), lambda x: True,
                              max_iterations=1, fixed_position=True)
    np.testing.assert_allclose(actual.mean, step, atol=1e-12)
