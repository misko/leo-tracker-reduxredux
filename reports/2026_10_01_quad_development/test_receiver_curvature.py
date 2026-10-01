import numpy as np
from receiver_curvature import basis, fit, folds, loss


def test_common_time_shift_preserves_quadratic_model_span():
    t = np.array([0., 1., 3., 4.]); rx = np.array([0, 0, 1, 1])
    B = np.array([[-1, 1, 0, 0], [0, 0, -1, 1]])
    original = basis(t, rx, B, 2., 0., 2.)
    shifted = basis(t, rx, B, 2., 1., 2.)
    np.testing.assert_allclose(shifted[:, :2], original[:, :2])
    np.testing.assert_allclose(shifted[:, 2:], original[:, 2:]-original[:, :2])
    np.testing.assert_allclose(basis(t+100, rx, B, 2., 100., 2.), original)


def test_robust_fit_recovers_shared_coefficients_with_outlier_group():
    rng = np.random.default_rng(73); beta = np.array([.4, -.8, 1.1, -.3]); rows = []
    for group in range(12):
        X = rng.normal(size=(7, 4)); y = X@beta
        if group == 0: y = y+50
        rows.append(dict(group=group, X=X, y=y))
    result = fit(rows, [0, 1, 2, 3])
    assert result['converged'] and np.all(np.diff(result['history']) <= 1e-8)
    np.testing.assert_allclose(result['beta'], beta, atol=.01)
    assert loss(rows, np.asarray(result['beta']), [0, 1, 2, 3]) < loss(rows, np.zeros(4), [0, 1, 2, 3])


def test_whole_satellite_groups_are_excluded_across_receivers():
    rows = [dict(group=g, rx=r) for g in (10, 20, 30) for r in (0, 1)]
    for group, train, check in folds(rows):
        assert len(check) == 2 and {r['rx'] for r in check} == {0, 1}
        assert all(r['group'] != group for r in train)
        assert all(r['group'] == group for r in check)


def test_unidentified_training_is_explicit_failure():
    row = dict(group=1, y=np.ones(4), X=np.zeros((4, 4)))
    assert fit([row], [0, 1])['reason'] == 'rank_deficient'
    assert fit([], [0, 1])['reason'] == 'empty_training'
