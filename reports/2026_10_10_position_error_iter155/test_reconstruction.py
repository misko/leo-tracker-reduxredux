"""Synthetic construction/audit ports only; no optimizer or recording access."""
import copy
from types import SimpleNamespace

import numpy as np
import pytest

from reconstruction import b7_seed, reconstruct


def fixture():
    vector = [1., 2., 0., 0., 0., 0., 0., 0.]
    clock = [0., 0., 0., 0.]
    state = dict(stage='B7', vector=vector, clock_coefficients=clock,
                 receiver_baseline_hz=[0., 0.], clock_nodes_s=[0., 1., 2.],
                 satellite_centers_s=[0., 0.], total_objective=10.)
    fit = dict(vector=vector, clock_coefficients=clock, objective=10.,
               converged=True, joint_state=state)
    operation = dict(arm='zero-c', accepted_stage='B7', satellites=[11, 12], fit=fit,
                     seed_audit={'effective': [99., 99.]})
    attempts = {name: {'fitted-c': dict(vector=[x, 0., 0., 0., 0., 0., 0., 0.], converged=True)}
                for name, x in [('B3', 3.), ('B4', 4.), ('B4W', 5.), ('B5', 6.)]}
    attempts['B7'] = {'zero-c': copy.deepcopy(fit)}
    receipt = dict(status='complete', branch='native', operational={'zero-c': operation}, attempts=attempts)
    model = SimpleNamespace(size=8, smooth_clock_count=2, fixed_rf_drift=False,
                            bank=SimpleNamespace(numbers=np.array([11, 12])))

    def construct(case, selected, components):
        assert set(selected) == {'selection', 'fit'}
        assert selected['selection'] == {'accepted_stage': 'B7', 'satellites': [11, 12]}
        return model, np.array(selected['fit']['vector']), np.array(selected['fit']['clock_coefficients'])

    class Problem:
        def __init__(self, model, original, **options):
            self.original = original.copy()
            self.start = original.copy(); self.start[7] += 1e-10
            self.options = options
            assert options['local_radius_km'] == 25
            assert options['rf_arm'] == 'zero-c'
            assert not options['fixed_position']
        def feasible(self, value):
            return np.array_equal(value, self.original)
        def stationarity(self, vector, gradient):
            return float(np.max(abs(gradient)))

    return receipt, construct, Problem


@pytest.mark.parametrize('wide,dynamic,expected', [(True, True, 'B5'), (True, False, 'B4W'), (False, False, 'B4')])
def test_original_stage_seed_and_helper_projection_not_adopted(wide, dynamic, expected):
    receipt, construct, problem = fixture()
    receipt['attempts']['B4W']['fitted-c']['converged'] = wide
    receipt['attempts']['B5']['fitted-c']['converged'] = dynamic
    before = copy.deepcopy(receipt)
    result = reconstruct(None, receipt, 'zero-c', construct=construct, components={}, problem_type=problem)
    assert result['seed_stage'] == expected
    np.testing.assert_array_equal(result['local_center'], receipt['attempts'][expected]['fitted-c']['vector'][:2])
    assert result['helper_projection_delta'][7] != 0
    assert result['vector'][7] == 0
    assert result['feasible'](result['vector'], result['clock'])
    assert receipt == before


def test_locked_rf_gradient_excluded_but_smooth_gradient_audited():
    receipt, construct, problem = fixture()
    result = reconstruct(None, receipt, 'zero-c', construct=construct, components={}, problem_type=problem)
    args = (result['vector'], result['clock'], np.zeros(8))
    audit = result['anchor_audit'](*args, np.array([0., 0., 9., -9.]), 'zero-c')
    assert audit['qualified'] and audit['stationarity'] == 0
    audit = result['anchor_audit'](*args, np.array([.01, 0., 9., -9.]), 'zero-c')
    assert not audit['qualified'] and audit['clock_stationarity'] == .5
    changed = result['clock'].copy(); changed[-1] = .1
    assert not result['feasible'](result['vector'], changed)


@pytest.mark.parametrize('change', ['attempt', 'stage', 'chain', 'clock-lock', 'physical-lock'])
def test_invalid_identity_or_state_rejected(change):
    receipt, construct, problem = fixture()
    if change == 'attempt': receipt['attempts']['B7']['zero-c']['objective'] = 11.
    if change == 'stage': receipt['operational']['zero-c']['accepted_stage'] = 'C6'
    if change == 'chain': receipt['attempts']['B3']['fitted-c']['converged'] = False
    if change in ('clock-lock', 'physical-lock'):
        key, index = ('clock_coefficients', -1) if change == 'clock-lock' else ('vector', 6)
        for fit in (receipt['operational']['zero-c']['fit'], receipt['attempts']['B7']['zero-c']):
            fit[key][index] = 1.
    with pytest.raises((ValueError, AssertionError)):
        reconstruct(None, receipt, 'zero-c', construct=construct, components={}, problem_type=problem)
