import numpy as np

from leo.analysis.localization_influence import group_deletion_steps


def test_deletion_matches_exact_linear_refit_and_coordinate_rescaling():
    rng = np.random.default_rng(10)
    designs = rng.normal(size=(4, 7, 5))
    values = rng.normal(size=(4, 7))
    prior = np.diag([0., 0., 1., 4., 4.])
    parts = np.array([a.T@a for a in designs])
    h = prior+parts.sum(axis=0)
    scores_zero = np.array([a.T@y for a, y in zip(designs, values, strict=True)])
    estimate = np.linalg.solve(h, scores_zero.sum(axis=0))
    scores = scores_zero-np.einsum('gij,j->gi', parts, estimate)
    rhs = scores.sum(axis=0)-prior@estimate
    result = group_deletion_steps(h, rhs, parts, scores)
    units = np.geomspace(1e-5, 1e5, 5)
    scaled = group_deletion_steps(
        h*units[:, None]*units, rhs*units, parts*units[None, :, None]*units,
        scores*units)
    for i, (r, s) in enumerate(zip(result, scaled, strict=True)):
        exact = np.linalg.solve(h-parts[i], scores_zero.sum(axis=0)-scores_zero[i])
        assert r.reason == s.reason == 'ok'
        np.testing.assert_allclose(estimate+r.step, exact, atol=1e-12)
        np.testing.assert_allclose(s.step*units, r.step, atol=1e-12)


def test_rank_loss_is_recorded_without_silently_regularizing():
    result = group_deletion_steps(np.eye(2), np.zeros(2),
                                  np.array([np.diag([1., 0.])]), np.ones((1, 2)))
    assert result[0].step is None and result[0].reason == 'not_positive_definite'
