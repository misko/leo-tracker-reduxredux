"""Synthetic real-constraint audits; no production optimizer or recording work."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace as NS

import numpy as np
import pytest
from leo.analysis.hard60_bounded_fit import _Problem

SPEC=importlib.util.spec_from_file_location('fit_core163_test',Path(__file__).with_name('fit_core.py'))
CORE=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(CORE)


def fixture():
    model=NS(size=9,initial_clock=np.zeros(4),fixed_rf_drift=False,prior=NS(radius_km=100.),
        bank=NS(numbers=np.array([1,2]),nodes_s=np.array([-100.,100.])),
        observations=NS(times_s=np.array([-1.,1.])),basis=np.array([[1.],[-1.]])/np.sqrt(2))
    model.evaluate_joint=lambda v,c:(12.,np.r_[100.,-100.,np.zeros(7)],np.zeros(4),NS(nll=10.))
    seed=np.zeros(9);seed[:2]=[2.,3.];seed[6]=250.
    clock=np.array([3.,4.,50.,-50.]);calls=[]
    def fit(objective,v,**options):
        calls.append((v.copy(),options['clock_seed'].copy(),options))
        assert options['fixed_position'] is True
        assert options['maximum_seconds']==90 and options['maximum_iterations']==600
        assert options['timing_half_width_s']==20
        return dict(vector=v.copy(),clock_coefficients=options['clock_seed'].copy(),objective=12.,
                    solver_success=True,converged=True)
    return model,seed,clock,fit,calls


def test_nonzero_fitted_start_preserved_and_spatial_gradient_projected():
    model,v,c,fit,calls=fixture();before=v.copy();clock_before=c.copy()
    result=CORE.execute_cell(model,v,c,arm='fitted-c',fit_port=fit,problem_type=_Problem)
    assert result['status']=='qualified' and result['audit']['position_locked']
    assert result['audit']['stationarity']==0 and result['audit']['prior_penalty']==2
    np.testing.assert_array_equal(calls[0][0],before)
    np.testing.assert_array_equal(calls[0][1],clock_before)
    np.testing.assert_array_equal(v,before);np.testing.assert_array_equal(c,clock_before)


def test_zero_start_projection_required_from_caller_not_silently_applied():
    model,v,c,fit,calls=fixture()
    result=CORE.execute_cell(model,v,c,arm='zero-c',fit_port=fit,problem_type=_Problem)
    assert result['status']=='failed' and not calls
    assert v[6]==250 and c[-1]==-50
    v[6]=0.;c[-2:]=0.
    result=CORE.execute_cell(model,v,c,arm='zero-c',fit_port=fit,problem_type=_Problem)
    assert result['status']=='qualified' and len(calls)==1


@pytest.mark.parametrize('fault',['static-bound','rf-bound','smooth-bound','timing','slope','nan'])
def test_invalid_fitted_start_not_projected_into_valid_state(fault):
    model,v,c,fit,calls=fixture()
    if fault=='static-bound':v[6]=5001
    if fault=='rf-bound':c[-1]=1001
    if fault=='smooth-bound':c[0]=2001
    if fault=='timing':v[8]=100
    if fault=='slope':v[3]=61
    if fault=='nan':c[0]=np.nan
    result=CORE.execute_cell(model,v,c,arm='fitted-c',fit_port=fit,problem_type=_Problem)
    assert result['status']=='failed' and not calls


@pytest.mark.parametrize('fault',['position','static-lock','rf-lock','clock-box','nonfinite','objective','kkt'])
def test_returned_failure_preserves_solver_state_and_cost(fault):
    model,v,c,original,_=fixture();v[6]=0.;c[-2:]=0.
    def fit(*a,**k):
        row=original(*a,**k)
        if fault=='position':row['vector'][0]+=1e-12
        if fault=='static-lock':row['vector'][6]=1e-20
        if fault=='rf-lock':row['clock_coefficients'][-1]=1e-20
        if fault=='clock-box':row['clock_coefficients'][0]=2001
        if fault=='nonfinite':row['vector'][2]=np.nan
        if fault=='objective':row['objective']=11.
        return row
    if fault=='kkt':
        model.evaluate_joint=lambda v,c:(12.,np.zeros(9),np.array([.01,0.,0.,0.]),NS(nll=10.))
    result=CORE.execute_cell(model,v,c,arm='zero-c',fit_port=fit,problem_type=_Problem)
    assert result['status'] in ('failed','unqualified') and result['solver']['solver_success']
    assert result['fit_elapsed_s'] is not None and result['audit_elapsed_s'] is not None


def test_clock_boundary_projection_and_rf_locked_gradient():
    model,v,c,fit,_=fixture();v[6]=0.;c[:]=[2000.,-2000.,0.,0.]
    model.evaluate_joint=lambda v,c:(12.,np.r_[100.,-100.,np.zeros(7)],np.array([-1.,1.,1.,-1.]),NS(nll=10.))
    result=CORE.execute_cell(model,v,c,arm='zero-c',fit_port=fit,problem_type=_Problem)
    assert result['status']=='qualified'


def test_solver_exception_cost_recorded_without_retry():
    model,v,c,_,_=fixture();now=[0.];calls=[]
    def fit(*a,**k):calls.append(1);now[0]=91.;raise RuntimeError('failure')
    result=CORE.execute_cell(model,v,c,arm='fitted-c',fit_port=fit,problem_type=_Problem,clock=lambda:now[0])
    assert result['status']=='failed' and len(calls)==1
    assert result['fit_elapsed_s']==91. and result['fit_exceeded_soft_budget']
    assert result['solver'] is None and result['audit_elapsed_s'] is None


def test_retained_state_audit_uses_one_callback_without_optimizer():
    model,v,c,_,_=fixture();calls=[];original=model.evaluate_joint
    def evaluate(*a):calls.append(1);return original(*a)
    model.evaluate_joint=evaluate
    row=CORE.audit_state(model,v,v,c,12.,arm='fitted-c',problem_type=_Problem)
    assert row['status']=='qualified' and calls==[1]
    assert row['fit_called'] is False and row['fit_elapsed_s'] is None
    assert row['audit_called'] and row['origin']=='retained-control-audit'
    row=CORE.audit_state(model,v,v,c,11.,arm='fitted-c',problem_type=_Problem)
    assert row['status']=='unqualified' and row['audit']['objective_delta']==1.


def test_retained_state_cannot_change_fixed_hypothesis():
    model,v,c,_,_=fixture();changed=v.copy();changed[0]+=1.
    row=CORE.audit_state(model,v,changed,c,12.,arm='fitted-c',problem_type=_Problem)
    assert row['status']=='failed' and not row['audit_called']
    assert row['solver']['vector'][0]==changed[0]
