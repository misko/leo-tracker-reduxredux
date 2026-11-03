from dataclasses import replace
import numpy as np
import run_variants as run


def result(value, converged, vector=None):
    return run.engine.PositionFit(np.zeros(10) if vector is None else vector,
        value, 0., 10., 0. if converged else .1, converged, False, 'synthetic', 1, .01)


def test_reset_changes_only_timing_and_slopes():
    v = np.arange(10, dtype=float)
    out = run.reset_seed(v)
    np.testing.assert_array_equal(out[[0,1,2,4,6]],v[[0,1,2,4,6]])
    assert not out[[3,5,7,8,9]].any()
    np.testing.assert_array_equal(v,np.arange(10))


def test_recovery_accepts_converged_state_even_if_failed_state_has_lower_score():
    states=[result(1.,False),result(.5,False),result(2.,True)]
    starts=[]
    def fake(obj,start,**kw):
        starts.append(np.asarray(start).copy())
        return states[len(starts)-1]
    chosen,calls=run.recover_fit(None,np.ones(10),fit_function=fake)
    assert chosen is states[2] and len(calls)==3
    assert not starts[2][7:].any()


def test_recovery_stops_after_success_and_coarse_selection_is_score_only():
    calls=[]
    def fake(obj,start,**kw):
        calls.append(1)
        return result(3.,True)
    chosen,_=run.recover_fit(None,np.ones(10),fit_function=fake)
    assert chosen.converged and len(calls)==1
    assert run.choose_coarse([result(3.,True),result(2.,False)]).objective==2.


def test_rf_gauge_oracle_and_gradient_on_actual_scan():
    from rf_model import RFObjective
    _,obs,bank,prior,score=run.data.load('N29')
    score=replace(score,relative_sigma_s=2.)
    region=next(run.read(p) for p in sorted((run.control_folder('N29')/'regions').glob('*.json')) if run.read(p)['status']=='complete')
    bank=bank.select(region['association']['selected_indices'])
    baseline=region['calibration']['receiver_baseline_hz']
    fast=RFObjective(run.engine.NativeObjective(obs,bank,prior,score,receiver_baseline_hz=baseline))
    slow=RFObjective(run.engine.PositionObjective(obs,bank,prior,score,receiver_baseline_hz=baseline),
        gauge=(fast.groups,fast.group_basis,fast.incidence))
    np.testing.assert_allclose(fast.base.design[:,[0,2,4]].T@fast.extra_design,0,atol=1e-9)
    np.testing.assert_allclose(fast.group_basis.T@fast.group_basis,np.eye(fast.size-fast.base_size),atol=1e-12)
    v=fast.augment(region['association']['initial_vector'])
    v[7:fast.base_size]=0.123
    v[fast.base_size:]=np.linspace(-20,20,fast.size-fast.base_size)
    a,g,_=fast.evaluate(v);b,h,_=slow.evaluate(v)
    np.testing.assert_allclose(a,b,atol=1e-6,rtol=0)
    np.testing.assert_allclose(g,h,atol=1e-6,rtol=1e-7)
    for i in [0,1,2,3,6,7,*range(fast.base_size,fast.size)]:
        step=1e-4 if i>=fast.base_size else 1e-5
        delta=np.eye(fast.size)[i]*step
        numeric=(slow.evaluate(v+delta)[0]-slow.evaluate(v-delta)[0])/(2*step)
        np.testing.assert_allclose(g[i],numeric,atol=2e-4,rtol=2e-5)


def test_augmented_fit_known_bound_optimum_and_zero_c():
    from types import SimpleNamespace
    from rf_model import fit_rf,Domain
    class Quadratic:
        size=11;base_size=9;limit_hz=150.
        prior=SimpleNamespace(radius_km=250.)
        bank=SimpleNamespace(numbers=np.array([1,2]),nodes_s=np.array([-100.,100.]))
        observations=SimpleNamespace(times_s=np.array([-1.,1.]))
        basis=np.array([[1.],[-1.]])/np.sqrt(2)
        groups=np.zeros((4,2))
        group_basis=np.array([[1.,0.],[0.,1.],[-1.,0.],[0.,-1.]])/np.sqrt(2)
        scales=np.array([1.,1.,200.,2.,200.,2.,200.,1.,1.,50.,50.])
        target=np.array([1.,2.,0.,80.,0.,-90.,100.,0.,0.,400.,-400.])
        def augment(self,v):return np.r_[v,np.zeros(2)] if len(v)==9 else np.asarray(v).copy()
        def evaluate(self,v):
            g=(v-self.target)/self.scales**2
            return .5*float((v-self.target)@g),g,SimpleNamespace(responsibilities=np.ones((2,2)),residual_hz=np.zeros((2,2)))
    obj=Quadratic()
    fit=fit_rf(obj,np.zeros(9),rf_arm='zero-c',maximum_seconds=5.)
    assert fit.converged
    np.testing.assert_allclose(fit.vector[[0,1,3,5,6,9,10]],
        [1.,2.,60.,-60.,0.,150*np.sqrt(2),-150*np.sqrt(2)],atol=1e-5)
    audit=Domain(obj,fit.vector,'zero-c',None,None).audit(fit.vector,obj.evaluate(fit.vector)[1])
    assert audit['converged'] and len(audit['rf_active_bounds'])==4


def test_holdout_partition_preserves_physical_clock_and_rf_origins():
    from rf_model import RFObjective
    from holdout import make_objective
    _,obs,bank,prior,score=run.data.load('N29')
    region=next(run.read(p) for p in sorted((run.control_folder('N29')/'regions').glob('*.json')) if run.read(p)['status']=='complete')
    bank=bank.select(region['association']['selected_indices'])
    baseline=region['calibration']['receiver_baseline_hz']
    factory=run.engine.PositionObjective
    full=RFObjective(factory(obs,bank,prior,score,receiver_baseline_hz=baseline))
    v=full.augment(region['association']['initial_vector'])
    v[full.base_size:]=10.
    midpoint=(obs.times_s.min()+obs.times_s.max())/2
    mask=obs.times_s<midpoint
    left=make_objective(factory,obs,bank,prior,score,baseline,full,mask,True)
    right=make_objective(factory,obs,bank,prior,score,baseline,full,~mask,True)
    a=full.evaluate(v)[2];b=left.evaluate(v)[2];c=right.evaluate(v)[2]
    np.testing.assert_allclose(a.nll,b.nll+c.nll,atol=1e-7,rtol=0)
    np.testing.assert_allclose(a.residual_hz[mask],b.residual_hz,atol=1e-8,rtol=0)
    np.testing.assert_allclose(a.residual_hz[~mask],c.residual_hz,atol=1e-8,rtol=0)
