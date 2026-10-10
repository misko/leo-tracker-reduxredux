"""Prepared endpoint-port tests; no recording or optimizer calls."""
from types import SimpleNamespace
import math

import numpy as np
import pytest

import endpoint


def fixture():
    model=SimpleNamespace(score=SimpleNamespace(sigma_hz=125.,clutter_rate=.2,detection_budget=1.),
        bank=SimpleNamespace(numbers=np.arange(4)),observations=SimpleNamespace(receiver=np.array([0,1])),
        clock_design=np.array([[1.,0,0,0],[0,1.,0,0]]),calls=0)
    def evaluate(v,c):
        model.calls+=1
        return 10.+.5*(c[0]**2+c[1]**2),np.zeros(8),np.array([c[0],c[1],0.,0.]),None
    model.evaluate_joint=evaluate
    class Modes:
        def __init__(self,wrapped,v,c,arm):
            self.model=wrapped;self.v=v;self.c=c
            self.anchor_value=wrapped.evaluate_joint(v,c)[0]
            self.direction=np.array([1.]);self.slices=(slice(0,1),slice(1,2))
            self.amplitudes=np.zeros(2);self.precision=1.;self.intervals=((-1.,1.),(-1.,1.))
        def scalar(self,r,a):
            c=self.c.copy();c[r]=a
            value,_,g,_=self.model.evaluate_joint(self.v,c)
            return dict(difference=value-self.anchor_value,gradient=g[r])
    args=dict(arm='zero-c',stored_objective=10.,stored_joint_objective=10.,conditional_factory=Modes,
              feasible=lambda v,c:True,anchor_audit=lambda *a:{'qualified':True},
              fingerprint=lambda:{'sha256':'same'},visibility_factory=lambda *a:np.array([[True,False,False,False],[True,True,False,False]]))
    return model,np.zeros(8),np.zeros(4),args


def test_bound_inputs_sign_normalization_and_call_accounting(monkeypatch):
    model,v,c,args=fixture();seen=[]
    def integrate(callback,lo,hi,**options):
        assert (lo,hi)==(-1.,1.) and options['maximum_calls']==512 and options['target_log_width']==5e-5
        value,gradient=callback(.25);assert value==-.03125 and gradient==-.25
        assert math.isfinite(options['seam_bound'](lo,hi))
        seen.append(options)
        return dict(status='target_met',bounds=dict(log_lower=0.,log_upper=0.,log_width=0.),ledger=[{'preserved':True}])
    monkeypatch.setattr(endpoint.ADAPTIVE,'integrate',integrate)
    row=endpoint.check(model,v,c,**args)
    assert row['status']=='passed' and row['actual_joint_calls']==3 and row['visibility_calls']==1
    assert row['normalized_marginal_bounds']['lower']==pytest.approx(10+math.log(2*math.pi))
    assert row['axes']['0']['integration']['ledger']==[{'preserved':True}]
    rho=np.array([1.,2.])*.25/(.75*125*np.sqrt(2*np.pi)*(.2/endpoint.ALIAS_HZ))
    np.testing.assert_allclose(row['bound_inputs']['rho'],rho)
    np.testing.assert_array_equal(v,np.zeros(8));np.testing.assert_array_equal(c,np.zeros(4))
    assert all('fingerprint_before' not in item for item in row['calls'])


def test_budget_exhaustion_keeps_both_full_ledgers(monkeypatch):
    model,v,c,args=fixture()
    def integrate(callback,*a,**kw):
        callback(0)
        return dict(status='budget_exhausted',ledger=[{'all_support':True}],bounds=dict(log_lower=-2.,log_upper=2.,log_width=4.))
    monkeypatch.setattr(endpoint.ADAPTIVE,'integrate',integrate)
    row=endpoint.check(model,v,c,**args)
    assert row['status']=='unresolved' and row['normalized_marginal_bounds'] is None
    assert all(row['axes'][str(r)]['status']=='budget_exhausted' for r in (0,1))


def test_expired_callback_preserves_axis_ledger_and_other_unattempted(monkeypatch):
    model,v,c,args=fixture();now=[0.]
    def integrate(callback,*a,**kw):
        now[0]=31.
        with pytest.raises(TimeoutError):callback(0.)
        return dict(status='callback_failed',ledger=[{'deadline':True}])
    monkeypatch.setattr(endpoint.ADAPTIVE,'integrate',integrate)
    row=endpoint.check(model,v,c,**args,begun=0.,clock=lambda:now[0])
    assert row['status']=='unresolved' and row['axes']['0']['status']=='deadline_exhausted'
    assert row['axes']['1']['status']=='unattempted'
    assert row['actual_joint_calls']==1 and row['joint_attempts']==2


@pytest.mark.parametrize('failure',['branch','clutter','visibility','lock','feasible','anchor','kkt','mutation'])
def test_invalid_admission_never_integrates(monkeypatch,failure):
    model,v,c,args=fixture()
    monkeypatch.setattr(endpoint.ADAPTIVE,'integrate',lambda *a,**k:pytest.fail('unexpected integration'))
    if failure=='branch':model.score.sigma_hz=1001
    if failure=='clutter':model.score.clutter_rate=0
    if failure=='visibility':args['visibility_factory']=lambda *a:np.ones((2,4))
    if failure=='lock':v[6]=1
    if failure=='feasible':args['feasible']=lambda *a:False
    if failure=='anchor':args['stored_joint_objective']=11.
    if failure=='kkt':args['anchor_audit']=lambda *a:{'qualified':False}
    if failure=='mutation':args['fingerprint']=lambda:{'counter':model.calls}
    row=endpoint.check(model,v,c,**args)
    assert row['status']=='failed' and row['error']
    assert row['axes']['0']['status']=='unattempted'


def test_deadline_starts_before_constructor(monkeypatch):
    model,v,c,args=fixture()
    args['visibility_factory']=lambda *a:pytest.fail('already expired')
    row=endpoint.check(model,v,c,**args,begun=0.,clock=lambda:31.)
    assert row['status']=='unresolved' and row['actual_joint_calls']==0


def test_real_adaptive_gaussian_encloses_normalized_mass():
    model,v,c,args=fixture()
    # No likelihood dependence on this mode: the callback is its proper prior.
    model.clock_design[:]=0.
    row=endpoint.check(model,v,c,**args,clock=lambda:0.)
    assert row['status']=='passed'
    exact=10.-2*math.log(math.erf(1/math.sqrt(2)))
    bounds=row['normalized_marginal_bounds']
    assert bounds['lower'] <= exact <= bounds['upper']
    assert bounds['width']<=1e-4
    counts=[]
    for axis in row['axes'].values():
        result=axis['integration']
        assert result['full_support_covered'] and result['actual_calls']<=512
        assert len(result['ledger'])==result['actual_calls']
        counts.append(result['actual_calls'])
    assert row['actual_joint_calls']==1+sum(counts)==model.calls


def test_receiver_guard_refuses_513th_callback_and_keeps_failure(monkeypatch):
    model,v,c,args=fixture()
    def integrate(callback,*a,**kw):
        for _ in range(512):callback(0.)
        with pytest.raises(ValueError,match='receiver call cap'):callback(0.)
        return dict(status='callback_failed',ledger=[{'guarded_attempts':513}])
    monkeypatch.setattr(endpoint.ADAPTIVE,'integrate',integrate)
    row=endpoint.check(model,v,c,**args,clock=lambda:0.)
    assert row['status']=='failed' and row['actual_joint_calls']==513
    assert row['joint_attempts']==513 and model.calls==513
    assert row['axes']['0']['scalar_callback_attempts']==512
    assert row['axes']['0']['integration']['ledger']==[{'guarded_attempts':513}]
    assert row['axes']['1']['status']=='unattempted'


def test_second_axis_seam_deadline_preserves_first_and_partial_ledger(monkeypatch):
    model,v,c,args=fixture();now=[0.];axes=[]
    def integrate(callback,lo,hi,**kw):
        callback(0.);axes.append(len(axes))
        if len(axes)==1:
            return dict(status='target_met',bounds=dict(log_lower=0.,log_upper=0.,log_width=0.),ledger=[{'first':True}])
        now[0]=31.
        with pytest.raises(TimeoutError):kw['seam_bound'](lo,hi)
        return dict(status='callback_failed',ledger=[{'second_called_before_deadline':True}])
    monkeypatch.setattr(endpoint.ADAPTIVE,'integrate',integrate)
    row=endpoint.check(model,v,c,**args,begun=0.,clock=lambda:now[0])
    assert row['status']=='unresolved' and row['actual_joint_calls']==3
    assert row['axes']['0']['status']=='target_met'
    assert row['axes']['1']['status']=='deadline_exhausted'
    assert row['axes']['1']['integration']['ledger']==[{'second_called_before_deadline':True}]
