"""Synthetic fixed-position audit guards; no optimizer or recording calls."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace as NS

import numpy as np
import pytest

SPEC=importlib.util.spec_from_file_location("fit_core162_test",Path(__file__).with_name("fit_core.py"))
CORE=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(CORE)


def fixture():
    model=NS(size=9,initial_clock=np.zeros(4),fixed_rf_drift=False,
             prior=NS(radius_km=100.),bank=NS(numbers=np.array([1,2]),nodes_s=np.array([-100.,100.])),
             observations=NS(times_s=np.array([-1.,1.])),basis=np.array([[1.],[-1.]])/np.sqrt(2))
    model.evaluate_joint=lambda v,c:(12.,np.r_[100.,-100.,np.zeros(7)],np.zeros(4),NS(nll=10.))
    seed=np.zeros(9);seed[:2]=[2.,3.]
    calls=[]
    def fit(objective, supplied, **options):
        calls.append(options)
        assert options['fixed_position'] is True
        assert options['maximum_seconds']==90 and options['maximum_iterations']==600
        assert options['timing_half_width_s']==20
        return dict(vector=supplied.copy(),clock_coefficients=options['clock_seed'].copy(),
                    objective=12.,solver_success=True,converged=True)
    return model,seed,fit,calls


def test_actual_problem_projects_spatial_gradient_and_preserves_exact_position():
    from leo.analysis.hard60_bounded_fit import _Problem
    model,seed,fit,calls=fixture()
    result=CORE.execute_cell(model,seed,np.zeros(4),arm='zero-c',fit_port=fit,problem_type=_Problem)
    assert result['status']=='qualified' and len(calls)==1
    assert result['audit']['position_locked'] and result['audit']['stationarity']==0
    assert result['audit']['prior_penalty']==2
    np.testing.assert_array_equal(result['solver']['vector'][:2],seed[:2])


@pytest.mark.parametrize('fault',['position','static-c','rf-time','clock-box','slope','timing'])
def test_actual_constraints_reject_false_solver_success(fault):
    from leo.analysis.hard60_bounded_fit import _Problem
    model,seed,original,_=fixture()
    def fit(*a,**k):
        row=original(*a,**k)
        if fault=='position':row['vector'][0]+=1e-12
        if fault=='static-c':row['vector'][6]=1e-20
        if fault=='rf-time':row['clock_coefficients'][-1]=1e-20
        if fault=='clock-box':row['clock_coefficients'][0]=2001.
        if fault=='slope':row['vector'][3]=61.
        if fault=='timing':row['vector'][8]=100.
        return row
    result=CORE.execute_cell(model,seed,np.zeros(4),arm='zero-c',fit_port=fit,problem_type=_Problem)
    assert result['status']=='failed' and result['solver']['solver_success']
    assert result['audit']['qualified'] is False
    if fault=='position':assert result['audit']['position_locked'] is False


def test_actual_zero_locks_project_clock_and_c_gradients_only_in_zero_arm():
    from leo.analysis.hard60_bounded_fit import _Problem
    model,seed,fit,_=fixture()
    gradient=np.zeros(9);gradient[:2]=1e6;gradient[6]=1.
    model.evaluate_joint=lambda v,c:(12.,gradient,np.array([0.,0.,1.,-1.]),NS(nll=10.))
    zero=CORE.execute_cell(model,seed,np.zeros(4),arm='zero-c',fit_port=fit,problem_type=_Problem)
    free=CORE.execute_cell(model,seed,np.zeros(4),arm='fitted-c',fit_port=fit,problem_type=_Problem)
    assert zero['status']=='qualified' and free['status']=='unqualified'


def test_failure_cost_and_state_survive_audit_exception():
    from leo.analysis.hard60_bounded_fit import _Problem
    model,seed,fit,_=fixture();now=[0.]
    def fail(*a):
        now[0]=4.
        raise RuntimeError('fresh objective failure')
    model.evaluate_joint=fail
    result=CORE.execute_cell(model,seed,np.zeros(4),arm='fitted-c',fit_port=fit,
                             problem_type=_Problem,clock=lambda:now[0])
    assert result['status']=='failed' and result['solver'] is not None
    assert result['audit_elapsed_s']==4 and result['audit']['position_locked']


def test_false_nonspatial_convergence_and_objective_mismatch():
    from leo.analysis.hard60_bounded_fit import _Problem
    model,seed,fit,_=fixture()
    gradient=np.zeros(9);gradient[2]=.1
    model.evaluate_joint=lambda v,c:(13.,gradient,np.zeros(4),NS(nll=10.))
    result=CORE.execute_cell(model,seed,np.zeros(4),arm='fitted-c',fit_port=fit,problem_type=_Problem)
    assert result['status']=='unqualified' and result['audit']['objective_delta']==1
    assert result['audit']['physical_stationarity']>.001
