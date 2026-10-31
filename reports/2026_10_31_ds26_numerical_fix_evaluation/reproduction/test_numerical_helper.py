import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import scipy.optimize as optimize

from numerical_helper import bounded_position_call,centered_minimize,patched_stages
from numerical_stage import run_stage


def problem():
    return SimpleNamespace(sky={'time_s':np.array([-20.,40.])},flat_times=np.array([0.,1.]),
        flat_labels=np.array([0,0]),labels=[0],reference=np.array([-15.]),linear_entries=[])


def test_selector_excludes_other_optimizers_dimensions_boxes_and_analytic_derivatives():
    box=[(-12.5,12.5)]*2
    assert bounded_position_call('L-BFGS-B',[0,0],box)
    assert not bounded_position_call('Powell',[0,0],box)
    assert not bounded_position_call('L-BFGS-B',[0],[(-12.5,12.5)])
    assert not bounded_position_call('L-BFGS-B',[0,0],[(-1,1)]*2)
    assert not bounded_position_call('L-BFGS-B',[0,0],box,jac=lambda x:x)


def test_explicit_annotation_limit15_is_overridden_and_aliases_restore(monkeypatch):
    import phase_reference_checks as phase
    import ds23_frequency_events as events
    p=problem();factory=lambda *a,**k:p
    monkeypatch.setattr(events,'make_event_problem',factory)
    original_phase=phase.phase_refresh;original_minimize=optimize.minimize
    with patched_stages(reference_limit_s=30,centered_lbfgsb=False) as state:
        assert optimize.minimize is original_minimize
        events.make_event_problem()
        updated,check=phase.phase_refresh(np.array([-15.2]),p.reference,limit_s=15.)
        np.testing.assert_allclose(updated,[-15.2])
        assert check['next_reference_domain']['curved']['in_domain']
        assert check['numerical_reference_limit_s']==30
        assert state['reference_updates'][0]['caller_limit_s']==15
    assert events.make_event_problem is factory
    assert phase.phase_refresh is original_phase


def test_predictive_bank_guard_rejects_update_and_restores_on_error(monkeypatch):
    import ds23_frequency_events as events
    import ds23_predictive_linear as linear
    import phase_reference_checks as phase
    p=problem();p.reference=np.zeros(1);p.linear_entries=[{}]
    monkeypatch.setattr(events,'make_event_problem',lambda *a,**k:p)
    monkeypatch.setattr(linear,'linear_geometry',lambda *a: (SimpleNamespace(flat_times=np.array([-10.]),flat_labels=np.array([0])),))
    original=phase.phase_refresh
    with pytest.raises(ValueError,match='no extrapolation'):
        with patched_stages(reference_limit_s=30):
            events.make_event_problem()
            phase.phase_refresh(np.array([-15.2]),p.reference)
    assert phase.phase_refresh is original


def test_no_unchecked_refresh_without_captured_problem():
    import phase_reference_checks as phase
    with patched_stages(reference_limit_s=30):
        with pytest.raises(ValueError,match='no captured event problem'):
            phase.phase_refresh(np.zeros(1),np.zeros(1))


def test_centered_result_preserves_scipy_fields_and_counts_derivative_calls():
    calls=[]
    def objective(x,a,b):
        calls.append(np.array(x))
        return float((x[0]-a)**2+2*(x[1]-b)**2)
    original=optimize.minimize
    with patched_stages(reference_limit_s=30,centered_lbfgsb=True) as state:
        result=optimize.minimize(objective,np.array([1.,-2.]),args=(.5,-.25),method='L-BFGS-B',
            bounds=[(-12.5,12.5)]*2,options=dict(maxfun=240,maxiter=48,eps=.001,gtol=1e-4,maxls=20))
    assert optimize.minimize is original
    assert isinstance(result,optimize.OptimizeResult)
    assert result.success
    np.testing.assert_allclose(result.x,[.5,-.25],atol=1e-4)
    for key in ('x','fun','success','message','status','nit','nfev','njev','jac','hess_inv'):
        assert key in result
    np.testing.assert_array_equal(calls[0],[1.,-2.])
    assert result.nfev==len(calls)<=240
    assert result.numerical_maxls==40
    assert state['optimizer_calls'][0]['cap']==240
    assert state['extra_optimizer_rounds']==0


def test_hard_budget_cannot_report_success_or_hide_derivative_evaluations():
    calls=[]
    def objective(x):calls.append(1);return float(x@x)
    result=centered_minimize(optimize.minimize,objective,np.array([1.,-2.]),
        bounds=[(-12.5,12.5)]*2,options=dict(maxfun=2,maxiter=48))
    assert not result.success
    assert result.nfev==len(calls)==2
    assert result.status!=0
    assert np.isfinite(np.r_[result.x,result.fun,result.jac]).all()
    assert not result.jac_available


def test_boundary_derivatives_never_evaluate_outside_original_box():
    points=[]
    def objective(x):
        points.append(np.array(x));assert np.all(abs(x)<=12.5)
        return float(-x.sum())
    result=centered_minimize(optimize.minimize,objective,np.array([12.5,-12.5]),
        bounds=[(-12.5,12.5)]*2,options=dict(maxfun=240,maxiter=48,gtol=1e-4))
    assert result.success
    np.testing.assert_allclose(result.x,[12.5,12.5])
    assert result.nfev==len(points)<=240


def test_runpy_bootstrap_captures_policy_and_restores_state(tmp_path,monkeypatch):
    import ds23_frequency_events as events
    monkeypatch.setattr(events,'make_event_problem',lambda *a,**k:problem())
    script=tmp_path/'frozen_stage.py';receipt=tmp_path/'numerics.json'
    script.write_text('from ds23_frequency_events import make_event_problem\n'
        'from phase_reference_checks import phase_refresh\n'
        'import numpy as np\n'
        'p=make_event_problem()\n'
        'value,check=phase_refresh(np.array([-15.2]),p.reference,limit_s=15.)\n'
        'assert value[0]==-15.2\n')
    run_stage(script,[],reference_limit_s=30,centered_lbfgsb=True,receipt=receipt)
    record=json.loads(receipt.read_text())
    assert record['problem_count']==1
    assert record['reference_updates'][0]['numerical_reference_limit_s']==30
    assert record['restored_aliases']>0
    assert record['script_sha256']


def test_bootstrap_failure_still_records_and_restores(tmp_path):
    import phase_reference_checks as phase
    original=phase.phase_refresh;script=tmp_path/'failed.py';receipt=tmp_path/'receipt.json'
    script.write_text("raise RuntimeError('bounded failure')\n")
    with pytest.raises(RuntimeError,match='bounded failure'):
        run_stage(script,[],reference_limit_s=30,centered_lbfgsb=False,receipt=receipt)
    assert phase.phase_refresh is original
    assert json.loads(receipt.read_text())['stage_exception']['type']=='RuntimeError'


def test_runpy_main_from_import_gets_counted_centered_optimizer(tmp_path):
    script=tmp_path/'main_optimizer.py';receipt=tmp_path/'numerics.json'
    script.write_text('from scipy.optimize import minimize as position_minimize\n'
        'import numpy as np\n'
        'r=position_minimize(lambda x:float((x[0]-.5)**2+2*(x[1]+.25)**2),[1.,-2.],\n'
        'method="L-BFGS-B",bounds=[(-12.5,12.5)]*2,options={"maxfun":240,"maxiter":48})\n'
        'assert r.success and r.numerical_maxls==40\n'
        'assert r.nfev==r.total_physical_objective_evaluations<=240\n'
        'assert np.max(abs(r.x-np.array([.5,-.25])))<.0001\n')
    run_stage(script,[],reference_limit_s=30,centered_lbfgsb=True,receipt=receipt)
    record=json.loads(receipt.read_text())
    assert len(record['optimizer_calls'])==1
    assert record['optimizer_calls'][0]['start']==[1.,-2.]


def test_wrong_reference_owner_and_out_of_bank_final_posterior_are_rejected(monkeypatch):
    import ds23_frequency_events as events
    import phase_reference_checks as phase
    p=problem();monkeypatch.setattr(events,'make_event_problem',lambda *a,**k:p)
    with patched_stages(reference_limit_s=15):
        events.make_event_problem()
        with pytest.raises(ValueError,match='reference owner'):
            phase.phase_refresh(np.array([-15.2]),np.array([0.]))
        # The clipped next reference is in the bank; its unclipped physical
        # posterior is not. The guard must not hide that behind clipping.
        with pytest.raises(ValueError,match='no extrapolation'):
            phase.phase_refresh(np.array([-20.]),p.reference)
