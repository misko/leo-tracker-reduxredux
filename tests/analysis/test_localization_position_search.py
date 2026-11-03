import time

import numpy as np
import pytest

from leo.analysis.localization_position_search import fit_position_objective


def test_recovers_coupled_quadratic_and_descends():
    hessian = np.array([[3., .8], [.8, .4]])
    target = np.array([2., -3.])

    def objective(x):
        d = x-target
        return .5*d@hessian@d+10.

    result = fit_position_objective(
        np.array([-10., 8.]), objective, lambda p: np.linalg.norm(p) <= 250.,
        deadline=time.monotonic()+2)
    assert result.converged
    np.testing.assert_allclose(result.position, target, atol=1e-7)
    assert np.all(np.diff(result.objectives) < 0)


def test_expired_deadline_never_calls_objective():
    def forbidden(_):
        raise AssertionError('objective called after deadline')

    result = fit_position_objective(np.zeros(2), forbidden, lambda _: True,
                                    deadline=time.monotonic()-1)
    assert not result.converged and result.reason == 'wall_budget'
    assert not result.objectives


def test_boundary_and_invalid_inputs_are_not_success():
    result = fit_position_objective(np.zeros(2), lambda x: -x[0],
                                    lambda x: x[0] <= 0, deadline=time.monotonic()+2)
    assert not result.converged and result.reason == 'infeasible_stencil'
    with pytest.raises(ValueError):
        fit_position_objective(np.zeros(3), lambda _: 0., lambda _: True,
                               deadline=time.monotonic()+2)
