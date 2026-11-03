import time

import numpy as np

from leo.analysis.localization_joint_search import fit_joint_objective


def test_anisotropic_rotated_quadratic():
    a = np.array([[100., 3.], [3., .1]])
    target = np.array([.4, -3.])

    def objective(x):
        d = x-target
        return .5*d@a@d, a@d

    result = fit_joint_objective([2., 5.], objective, a, lambda x: True,
                                 deadline=time.monotonic()+2, max_metric_step=100.)
    assert result.converged
    np.testing.assert_allclose(result.mean, target, atol=1e-10)


def test_nonlinear_descent_and_bounded_support():
    evaluated = []

    def objective(x):
        evaluated.append(x.copy())
        return (x[0]-.3)**4+(x[1]+.2)**2, np.array([4*(x[0]-.3)**3, 2*(x[1]+.2)])

    result = fit_joint_objective([.9, .8], objective, np.eye(2),
        lambda x: np.all(np.abs(x) <= 1), deadline=time.monotonic()+2)
    assert result.converged
    assert all(np.max(np.abs(x)) <= 1 for x in evaluated)
    assert np.all(np.diff(result.objectives) <= 0)
    assert result.objectives[-1] < 1e-4


def test_no_false_success_on_inconsistent_gradient_or_expired_budget():
    result = fit_joint_objective([0.], lambda x: (0., np.ones(1)), np.eye(1), lambda x: True,
                                 deadline=time.monotonic()+2)
    assert not result.converged and result.reason == 'no_descent'
    result = fit_joint_objective([0.], lambda x: (0., np.ones(1)), np.eye(1), lambda x: True,
                                 deadline=time.monotonic()-1)
    assert not result.converged and result.reason == 'wall_budget'
