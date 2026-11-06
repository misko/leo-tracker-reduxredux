"""Observer retains original update bytes; Jacobian checks use a known map."""

import numpy as np
import pytest
from check_algo07v3_scan_likelihood import fingerprint
from profile_algo07v3_precision_coupling import factory, jacobian
from profile_algo07v3_precision_trajectory import Trajectory, observed


@pytest.mark.parametrize('learned', [False, True])
@pytest.mark.parametrize('implementation', ['owned', 'previous', 'fixed_prior_candidate'])
def test_all_original_transitions_exact(learned, implementation, monkeypatch):
    if implementation != 'owned':
        import importlib.util
        from pathlib import Path

        import algo07v3_prefixed_prior_oracle as previous
        import profile_algo07v3_precision_coupling as coupling
        import profile_algo07v3_precision_trajectory as trajectory_module
        if implementation == 'fixed_prior_candidate':
            path = (Path(__file__).resolve().parents[2] /
                'reports/2026_11_06_algo07v3_fixed_priors/candidate-src/leo/analysis/'
                'localization_v3/hierarchical.py')
            spec = importlib.util.spec_from_file_location('fixed_prior_candidate',path)
            previous = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(previous)
        monkeypatch.setattr(coupling, 'hierarchical', previous)
        monkeypatch.setattr(trajectory_module, 'hierarchical', previous)
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
