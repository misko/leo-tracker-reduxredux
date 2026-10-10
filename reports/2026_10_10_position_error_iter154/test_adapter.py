"""Actual constraint/serialization ports with synthetic model; no optimizer."""
import copy
import json
from types import SimpleNamespace
import numpy as np
import pytest
from leo.analysis.hard60_bounded_fit import _Problem
from leo.analysis.regional_position_fit import PositionFit
from leo.application.regional_position_runner import json_value
from adapter import recovery_port
from ports import load, HERE


def test_actual_problem_c_gradient_lock_and_fixed_position():
    model=SimpleNamespace(size=9,prior=SimpleNamespace(radius_km=100),
        bank=SimpleNamespace(numbers=[1,2],nodes_s=np.array([-100,100])),
        observations=SimpleNamespace(times_s=np.array([0,1])),basis=np.array([[1],[-1]])/np.sqrt(2))
    vector=np.zeros(9);vector[:2]=[1,2]; gradient=np.zeros(9);gradient[6]=1
    zero=_Problem(model,vector,fixed_position=True,rf_arm='zero-c',slope_half_width_hz_s=60)
    free=_Problem(model,vector,fixed_position=True,rf_arm='fitted-c',slope_half_width_hz_s=60)
    assert zero.stationarity(vector,gradient)==0 and free.stationarity(vector,gradient)==200
    moved=vector.copy();moved[0]+=1;assert not zero.feasible(moved)


@pytest.mark.parametrize('arm', ['zero-c', 'fitted-c'])
@pytest.mark.parametrize('mode', ['success', 'coupled-timing', 'audit-error', 'downstream-error'])
def test_actual_problem_repair_and_receipt_preservation(arm, mode):
    vector = np.zeros(9); vector[:2] = [1, 2]
    saved = json_value(PositionFit(vector, 3, None, 0, 0, False, False, 'seed', 1, 0))
    class Model:
        size = 9
        prior = SimpleNamespace(radius_km=100)
        bank = SimpleNamespace(numbers=[1, 2], nodes_s=np.array([-100, 100]))
        observations = SimpleNamespace(times_s=np.array([0, 1]))
        basis = np.array([[1], [-1]]) / np.sqrt(2)
        def evaluate(self, value):
            if mode == 'audit-error' and value[2] == 1:
                raise RuntimeError('synthetic NNLS audit failure')
            gradient = np.zeros(9)
            gradient[2] = 0 if value[2] == 1 else .01
            return (2 if value[2] == 1 else 3), gradient, None
    calls = []
    def bounded(model, start, **options):
        calls.append(options)
        assert options == dict(rf_arm=arm, fixed_position=True,
                               slope_half_width_hz_s=60, maximum_seconds=5,
                               maximum_iterations=200)
        start[2] = 1
        if mode == 'coupled-timing': start[8] = 40
        fit = PositionFit(start, 2, None, 0, 0, True, False, 'repair', 7, .1)
        return fit, dict(terminal=fit, solver_success=np.bool_(True))
    def fresh(*args):
        if mode == 'downstream-error': raise RuntimeError('calibration failure')
        return dict(status='qualified', calibration={'fresh': True})
    direct = SimpleNamespace(continuation=SimpleNamespace(_Problem=_Problem, fit_bounded_position=bounded),
                             qualification=SimpleNamespace(qualify=lambda *a, **k:pytest.fail('no102ownrepair')),
                             validated_postfit=lambda m, f, p:f, fresh_calibration=fresh)
    env = dict(direct=direct, np=np, core=SimpleNamespace(json_value=json_value),
               verify_coarse=lambda *a:(Model(), saved))
    exec('def recovered_region(o,b,p,t,s):\n return recover_calibration(o,b,p,t)', env)
    before = copy.deepcopy(saved)
    transition = load('transition150_adaptertest154', HERE.parent/'2026_10_10_position_error_iter150/transition.py')
    row = recovery_port({'recovered_region': env['recovered_region']}, arm, transition)(
        None, None, None, dict(key='point:1:2', original={'bootstrap':{'satellite_indices':[0,1]}}), None)
    assert saved == before and len(calls) == 1
    own = row['own_arm']; assert own['repair']['solver']['terminal']['evaluations'] == 7
    assert own['repair']['fit']['vector'][6] == 0
    assert own['cost_events'] and own['elapsed_s'] >= 0
    if mode == 'success': assert row['calibration'] == {'fresh': True}
    else: assert row['calibration'] is None
    if mode == 'coupled-timing': assert not own['repair']['audit']['feasible']
    if mode == 'audit-error': assert own['repair']['fit'] and own['repair']['solver']
    json.dumps(row, allow_nan=False)
