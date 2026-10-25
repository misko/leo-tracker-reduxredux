"""Small Gaussian identities and response-free D posterior; no corpus work."""
from types import SimpleNamespace
from unittest.mock import patch
import time
import numpy as np
import pytest
import prediction02 as p


def small_context(n=9):
    rng=np.random.default_rng(2026102551)
    u=rng.normal(size=(n,4))*.3
    cd=dict(target_track=dict(times=np.linspace(0,7,n),rf_hz=11.5e9),
        scan=SimpleNamespace(radio_sigma_hz=1.,fixed_window_noise=dict(extra_parameter_BIC_gain=0)),
        target=dict(phase_nu=3.,phase_mean_s=.2,phase_sd_s=1.5))
    base=dict(raw=rng.normal(size=n),covariance=np.eye(n)*2+u@u.T,q=np.linspace(.98,1.02,n),
        owners=[dict(observation_ids=['id'+str(i) for i in range(n)])],x=np.zeros(2))
    return cd,base


def dense_cost(raw,cov,shape,shift):
    sigma=cov+shape@shape.T
    root=np.linalg.cholesky(sigma)
    white=np.linalg.solve(root,raw+shift)
    return white@white+2*np.log(np.diag(root)).sum()+len(raw)*np.log(2*np.pi)


def test_same_mixed_exact_D_marginal_and_independent_81_alias_measure():
    cd,base=small_context()
    same=p.setup(cd,np.zeros(2),base,np.arange(9),5,'same')
    mixed=p.setup(cd,np.zeros(2),base,np.arange(9),5,'mixed')
    np.testing.assert_array_equal(same['covariance'][:5],mixed['covariance'][:5])
    np.testing.assert_array_equal(mixed['polynomial_columns'][:5],0)
    np.testing.assert_array_equal(same['q'],same['native_q'])
    np.testing.assert_array_equal(mixed['q'][:5],same['q'][:5])
    np.testing.assert_array_equal(mixed['q'][5:],0)
    assert same['aliases'].shape==(81,2)
    assert np.array_equal(same['aliases'],mixed['aliases'])
    assert np.array_equal(np.unique(same['aliases'][:,0],return_counts=True)[1],np.full(9,9))
    assert np.array_equal(same['covariance'][:5,5:],base['covariance'][:5,5:])


def test_positive_joint_densities_and_joint_minus_D_schur_identity():
    cd,base=small_context();rng=np.random.default_rng(444)
    shape=rng.normal(size=(9,3))*.2
    for model in ('same','mixed'):
        comp=p.setup(cd,np.zeros(2),base,np.arange(9),5,model)
        actual_shape=shape.copy()
        if model=='mixed':actual_shape[5:]=0
        # A modest finite period tests normalization without broad-covariance
        # roundoff obscuring the identity itself.
        aliases,shifts=p.k.alias_vectors(comp['groups'],np.arange(-4,5));shifts=shifts/p.k.PERIOD*3.7
        costs=p.sr.sm.positive_costs(comp['raw'][None],comp['covariance'],actual_shape[None],shifts)[0]
        direct=np.array([dense_cost(comp['raw'],comp['covariance'],actual_shape,shift) for shift in shifts])
        np.testing.assert_allclose(costs,direct,atol=1e-11,rtol=0)
        full=comp['covariance']+actual_shape@actual_shape.T
        dd=full[:5,:5];wd=full[5:,:5]
        conditional=full[5:,5:]-wd@np.linalg.solve(dd,wd.T)
        for shift,cost in zip(shifts,costs,strict=True):
            raw=comp['raw']+shift
            dcost=dense_cost(raw[:5],dd,np.empty((5,0)),np.zeros(5))
            wc=raw[5:]-wd@np.linalg.solve(dd,raw[:5])
            wcost=dense_cost(wc,conditional,np.empty((4,0)),np.zeros(4))
            assert abs(cost-dcost-wcost)<1e-10


def diagnostic_fixture():
    cd,base=small_context(61)
    groups=np.r_[np.zeros(57,int),np.ones(4,int)]
    base['covariance']=base['covariance']+300**2*(groups[:,None]==groups[None,:])
    times=np.linspace(0,7,61);cd['target_track']['times']=times
    phase_gain=np.linspace(-.4,.7,61)
    shape=np.column_stack((np.ones(61)*.3,np.linspace(-.2,.4,61),np.sin(times)*.1))
    def geometry(d,x,phases):
        ph=np.asarray(phases)
        return dict(frequency_hz=ph[:,None]*phase_gain[None],
            shape_columns_hz=np.broadcast_to(shape,(len(ph),61,3)).copy(),elevation_deg=np.ones((len(ph),61)))
    def support(*args,**kwargs):
        return dict(certified=True,root_brackets=[],inner_visible_intervals=[[-15.,15.]],interpolation_breakpoints=[-15.,15.])
    cd['target_sky']={}
    return cd,base,geometry,support


def test_Donly_prediction_and_posterior_are_invariant_to_all_W_responses():
    cd,base,geometry,support=diagnostic_fixture()
    with patch.object(p.k.m.q,'phase_geometry',side_effect=geometry),patch.object(p,'supports',side_effect=support):
        first=p.diagnostic_rule(cd,base,32,time.monotonic()+20)
        changed=dict(base,raw=base['raw'].copy());changed['raw'][57:]=[1e8,-1e9,3e7,-4e7]
        second=p.diagnostic_rule(cd,changed,32,time.monotonic()+20)
    for key in ('objective','phase_mean_s','phase_SD_s','shape_mean','shape_covariance',
        'Dconstant_mean_Hz','Dconstant_SD_Hz','alias_probabilities','prediction_mean_Hz','prediction_SD_Hz'):
        np.testing.assert_array_equal(first[key],second[key])
    assert not first['W_responses_used']


def test_Dposterior_predictive_moments_match_dense_gaussian_conditioning():
    cd,base,geometry,support=diagnostic_fixture()
    # Phase-invariant physical law makes the exact posterior an explicit
    # finite alias Gaussian mixture. No phase quadrature error is involved.
    fixed=geometry(cd,np.zeros(2),[0.])['shape_columns_hz'][0]*base['q'][:,None]
    def constant_geometry(d,x,phases):
        return dict(frequency_hz=np.zeros((len(phases),61)),
            shape_columns_hz=np.broadcast_to(fixed/base['q'][:,None],(len(phases),61,3)).copy(),elevation_deg=np.ones((len(phases),61)))
    with patch.object(p.k.m.q,'phase_geometry',side_effect=constant_geometry),patch.object(p,'supports',side_effect=support):
        actual=p.diagnostic_rule(cd,base,64,time.monotonic()+20)
    full=base['covariance']+fixed@fixed.T;dd=full[:57,:57];wd=full[57:,:57]
    conditional=full[57:,57:]-wd@np.linalg.solve(dd,wd.T)
    costs=[];means=[]
    for alias in range(-4,5):
        y=base['raw'][:57]+alias*p.k.PERIOD
        costs.append(dense_cost(y,dd,np.empty((57,0)),np.zeros(57)))
        means.append(wd@np.linalg.solve(dd,y))
    logs=-.5*np.array(costs);weights=np.exp(logs-p.logsumexp(logs));means=np.array(means)
    expected=weights@means
    variance=np.diag(conditional)+weights@(means**2)-expected**2
    np.testing.assert_allclose(actual['prediction_mean_Hz'],expected,atol=1e-6,rtol=0)
    np.testing.assert_allclose(actual['prediction_SD_Hz'],np.sqrt(variance),atol=1e-6,rtol=0)
    np.testing.assert_allclose(actual['alias_probabilities'],weights,atol=1e-12,rtol=0)
    # Dense latent mode and D-constant posterior mixture.
    y=base['raw'][:57]
    shape_mean=fixed[:57].T@np.linalg.solve(dd,y)
    constant_mean=300**2*np.ones(57)@np.linalg.solve(dd,y)
    np.testing.assert_allclose(actual['shape_mean'],shape_mean,atol=1e-6,rtol=0)
    assert abs(actual['Dconstant_mean_Hz']-constant_mean)<1e-6


def test_conditional_odds_use_common_D_denominator_and_strict_bounds():
    def row(l,u,objective):return dict(status='complete',certified_visibility=True,
        full_support_lower_log_integral=l,full_support_upper_log_integral=u,objective=objective)
    same,mixed,D=row(-10,-9,19.),row(-14,-13,27.),row(-5,-4,9.)
    result=p.compare(same,mixed,D)
    assert result['proved'] and result['winner']=='same_family'
    assert result['joint_log_evidence_odds_bounds']==[3.,5.]
    assert result['raw_conditional_same_minus_mixed_objective']==-8.
    assert result['same_conditional_log_evidence_bounds']==[-6.,-4.]
    assert p.compare(same,row(-9.5,-8.5,18.),D)['proved'] is False
    assert p.compare(dict(same,full_support_lower_log_integral=float('nan')),mixed,D)['proved'] is False


def test_support_mixed_is_Donly_and_retains_all_bank_cuts():
    cd,base=small_context();comp=p.setup(cd,np.zeros(2),base,np.arange(9),5,'mixed');cd['target_sky']={}
    calls=[]
    def support(bank,times,*args):
        calls.append(len(times))
        return dict(certified=True,root_brackets=[],inner_visible_intervals=[[-15.,15.]],
            interpolation_breakpoints=[-15.,.1 if len(times)==5 else .2,15.])
    with patch.object(p.sr.sg,'support',side_effect=support):result=p.supports(cd,comp)
    assert calls==[9,5]
    np.testing.assert_array_equal(result['interpolation_breakpoints'],[-15.,.1,.2,15.])


def test_no_expired_science_stage():
    with pytest.raises(TimeoutError):p.sr.alarm(0)


def test_Path_output_stem_writes_support_primary_and_final_artifacts():
    from pathlib import Path
    row=dict(objective=4.,numerically_qualified=True)
    comp=dict(d={},native_q=np.ones(3),q=np.ones(3),model='discovery',aliases=np.zeros((9,1),int))
    reference=dict(objective=4.,success=True)
    with patch.object(p,'supports',return_value={}),patch.object(p,'write') as write,patch.object(p.sr,'alarm'),patch.object(
        p.sr,'score_candidate',return_value=(row,lambda x:x,[],[])),patch.object(p.sr.sm,'reference',return_value=reference):
        result=p.evidence({},comp,Path('c0')/'D',time.monotonic()+10)
    assert result['numerically_qualified']
    assert [call.args[0] for call in write.call_args_list]==['c0/D_support.json','c0/D_primary_checkpoint.json','c0/D_evidence.json']
