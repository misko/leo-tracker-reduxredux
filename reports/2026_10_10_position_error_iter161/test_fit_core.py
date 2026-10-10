"""Injected port tests only; no recording, optimizer or reference access."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace as NS

import numpy as np
import pytest

SPEC = importlib.util.spec_from_file_location("fit_core161_test", Path(__file__).with_name("fit_core.py"))
CORE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CORE)


def fixture():
    model = NS(size=8, initial_clock=np.zeros(4), fixed_rf_drift=False, calls=0)
    def evaluate(vector, coefficients):
        model.calls += 1
        return 12., np.zeros(8), np.zeros(4), NS(nll=10.)
    model.evaluate_joint = evaluate
    class Problem:
        def __init__(self, objective, seed, **options):
            assert options['rf_arm'] in ('zero-c', 'fitted-c')
            assert options['fixed_position'] is False
            np.testing.assert_array_equal(options['local_center'], [0.,0.])
            assert options['local_radius_km']==25. and options['slope_half_width_hz_s']==60.
        def feasible(self, vector): return np.linalg.norm(vector[:2]) <= 25
        def stationarity(self, vector, gradient): return float(np.max(abs(gradient)))
    def fit(objective, seed, **options):
        assert options['maximum_seconds'] == 90 and options['maximum_iterations'] == 600
        assert options['timing_half_width_s'] == 20 and options['fixed_position'] is False
        seed[0] = 1.
        return dict(vector=seed, clock_coefficients=options['clock_seed'], objective=12.,
                    converged=True, solver_success=True, evaluations=3)
    return model, Problem, fit


def test_moving_position_audited_not_anchor_locked():
    model, problem, fit = fixture(); seed=np.zeros(8); initial=np.zeros(4)
    result=CORE.execute_cell(model, seed, initial, arm='zero-c', fit_port=fit, problem_type=problem)
    assert result['status']=='qualified' and model.calls==1
    assert result['solver']['vector'][0]==1 and seed[0]==0
    assert result['audit']['likelihood_nll']==10 and result['audit']['prior_penalty']==2


@pytest.mark.parametrize('fault', ['physical-gradient','clock-gradient','nan-gradient','objective',
                                  'position','static-lock','rf-lock','clock-box'])
def test_false_success_rejected_and_returned_state_preserved(fault):
    model, problem, original = fixture()
    if fault in ('physical-gradient','clock-gradient','nan-gradient','objective'):
        def evaluate(v,c):
            pg=np.zeros(8); cg=np.zeros(4)
            if fault=='physical-gradient': pg[0]=.002
            if fault=='clock-gradient': cg[0]=.00003
            if fault=='nan-gradient': cg[0]=np.nan
            return (13. if fault=='objective' else 12.),pg,cg,NS(nll=10.)
        model.evaluate_joint=evaluate
    def fit(*a,**k):
        row=original(*a,**k)
        if fault=='position': row['vector'][0]=26
        if fault=='static-lock': row['vector'][6]=1e-20
        if fault=='rf-lock': row['clock_coefficients'][-1]=1e-20
        if fault=='clock-box': row['clock_coefficients'][0]=2001
        return row
    result=CORE.execute_cell(model,np.zeros(8),np.zeros(4),arm='zero-c',fit_port=fit,problem_type=problem)
    assert result['status'] in ('failed','unqualified')
    assert result['solver']['solver_success'] is True
    assert result['audit_elapsed_s'] is not None


def test_zero_rf_gradient_is_projected_but_fitted_rf_gradient_is_not():
    model, problem, fit=fixture()
    model.evaluate_joint=lambda v,c:(12.,np.zeros(8),np.array([0.,0.,1.,1.]),NS(nll=10.))
    zero=CORE.execute_cell(model,np.zeros(8),np.zeros(4),arm='zero-c',fit_port=fit,problem_type=problem)
    free=CORE.execute_cell(model,np.zeros(8),np.zeros(4),arm='fitted-c',fit_port=fit,problem_type=problem)
    assert zero['status']=='qualified' and free['status']=='unqualified'


def test_solver_exception_retains_elapsed_cost_without_audit():
    model, problem, _=fixture(); now=[0.]
    def fit(*a,**k):
        now[0]=91.
        raise RuntimeError('solver failed')
    result=CORE.execute_cell(model,np.zeros(8),np.zeros(4),arm='zero-c',fit_port=fit,
                             problem_type=problem,clock=lambda:now[0])
    assert result['status']=='failed' and result['fit_elapsed_s']==91
    assert result['fit_exceeded_soft_budget'] and result['audit_elapsed_s'] is None
    assert result['solver'] is None and model.calls==0


def test_callback_failure_preserves_solver_and_audit_cost():
    model, problem, fit=fixture(); now=[0.]
    def evaluate(*args):
        now[0]=3.
        raise RuntimeError('audit failed')
    model.evaluate_joint=evaluate
    result=CORE.execute_cell(model,np.zeros(8),np.zeros(4),arm='fitted-c',fit_port=fit,
                             problem_type=problem,clock=lambda:now[0])
    assert result['solver'] is not None and result['audit_called']
    assert result['audit_elapsed_s']==3 and result['error']
