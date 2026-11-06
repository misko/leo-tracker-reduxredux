"""Observer retains original update bytes; Jacobian checks use a known map."""

import numpy as np
import pytest
from check_algo07v3_scan_likelihood import fingerprint
from profile_algo07v3_precision_coupling import factory, jacobian
from profile_algo07v3_precision_trajectory import Trajectory, observed


@pytest.mark.parametrize('learned', [False, True])
def test_all_original_transitions_exact(learned):
    rng = np.random.default_rng(34)
    args = (rng.normal(size=32), rng.normal(size=(32,5)), np.ones(32), np.arange(32)%4)
    kw = dict(prior_groups=np.arange(5)%2 if learned else None, iterations=20)
    trajectory = Trajectory()
    observed(trajectory.record)(*args, **kw)
    make, _, _ = factory()
    operation = make(*args, **kw)
    for row in trajectory.rows:
        actual = operation(np.array(row['rate']), np.array(row['prior_rate']))
        expected = (np.array(row['next_rate']), np.array(row['next_prior_rate']), row['change'])
        assert fingerprint(actual) == fingerprint(expected)


def test_log_jacobian_for_analytic_map():
    matrix = np.array([[.8, -.2], [.1, 1.03]])
    def transition(rate, prior):
        x = np.r_[rate, prior]
        y = np.exp(matrix@np.log(x))
        return y[:1], y[1:], 0.
    actual = jacobian(transition, np.array([2.]), np.array([3.]), 1e-4)
    np.testing.assert_allclose(actual, matrix, atol=2e-12, rtol=0)
