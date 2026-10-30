import numpy as np
import pytest
import include_predictive_annotations as trial


def test_continuation_uses_arm_specific_rf_state_without_mutating_it():
    policy = {arm: dict(endpoint_east_north_km=[k, -k], phase_reference=[k, .1, .2])
              for k, arm in enumerate(('c0', 'fitted_c'), 1)}
    for mode in ('incumbent_unconstrained', 'incumbent_elbo_unconstrained', 'incumbent_feasible'):
        x, ref = trial.position_initialization(policy, 'fitted_c', 3, mode)
        np.testing.assert_array_equal(x, [2, -2])
        np.testing.assert_array_equal(ref, [2, .1, .2])
        x[:] = 0; ref[:] = 0
    assert policy['fitted_c']['endpoint_east_north_km'] == [2, -2]
    x, ref = trial.position_initialization({}, 'c0', 3, 'regional_unconstrained')
    assert not x.any() and not ref.any()
    with pytest.raises(ValueError, match='invalid incumbent'):
        trial.position_initialization(policy, 'c0', 4, 'incumbent_feasible')


def test_feasible_step_preserves_gate_at_boundary_instead_of_free_minimum(monkeypatch):
    from types import SimpleNamespace
    import probe_algo03_feasible_recovery as gates
    entries = [dict(component='old'), dict(component='new')]
    seen = []
    def slacks(p, x, passed):
        seen.append(passed)
        return {'old/step': 1 - x[0], 'new/step': x[0] + 1}
    monkeypatch.setattr(gates, 'gate_slacks', slacks)
    p = SimpleNamespace(lower=np.array([-5., -5.]), upper=np.array([5., 5.]),
                        calculate=lambda x: {'negative_twice_elbo': (x[0]-2)**2 + x[1]**2})
    result = trial.position_step(p, np.zeros(2), entries, 'incumbent_feasible')
    assert result['feasible']
    assert .99 < result['parameters'][0] <= 1
    assert all(v is entries for v in seen)
    assert result['score'] >= 1  # unconstrained optimum violates the old gate
    free = trial.position_step(p, np.zeros(2), entries, 'incumbent_elbo_unconstrained')
    assert free['parameters'][0] > 1.99
    assert free['score'] < 1e-5
