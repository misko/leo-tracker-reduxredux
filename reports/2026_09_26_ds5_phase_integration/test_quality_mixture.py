import numpy as np
from scipy.special import logsumexp
from quality_mixture import run_mixture,compress
from causal_quality_accuracy import exact_evidence
from catalogue_trial import constant_log_evidence

def test_sufficient_components_retain_exact_short_histories():
    r=np.array([0.,3.,1.,60.,40.,15.]);times=np.arange(6.);flags=np.array([0,0,1,0,0,0],bool);scales=[5.,50.]
    for kind in ('stationary','generic','timing_informed'):
        rows=run_mixture(r[None,None,:],np.zeros((1,1)),scales,times,flags,kind,warmup=0,components=32)
        assert abs(sum(x['log_predictive'] for x in rows)-exact_evidence(r,scales,times,flags,kind))<1e-8

def test_compression_preserves_mass_mean_and_variance():
    w=np.log([[.05,.15,.1,.1,.2,.4]]);m=np.array([[-3,-2,0,1,2,4.]]);v=np.ones_like(m)*2
    a,b,c=compress(w,m,v,3);p=np.exp(w);q=np.exp(a)
    assert np.isclose(q.sum(),1)
    assert np.isclose((p*m).sum(),(q*b).sum())
    assert np.isclose((p*(v+m*m)).sum(),(q*(c+b*b)).sum())

def test_stationary_filter_stays_exact_with_extra_slots():
    rng=np.random.default_rng(92);r=rng.normal(size=(2,3,10))*30+1e5;lp=np.full((2,3),-np.log(6));scales=[5,20,100]
    rows=run_mixture(r,lp,scales,np.arange(10.),np.zeros(10,bool),'stationary',components=4,warmup=0)
    expected=logsumexp(np.stack([constant_log_evidence(r,s) for s in scales])+lp)-np.log(3)
    assert np.isclose(sum(x['log_predictive'] for x in rows),expected,atol=1e-7)

def test_future_data_and_flags_do_not_change_earlier_predictions():
    rng=np.random.default_rng(93);r=rng.normal(size=(1,2,10));lp=np.full((1,2),-np.log(2));f=np.zeros(10,bool);t=np.arange(10.)
    a=run_mixture(r,lp,[5,20],t,f,'timing_informed',components=4)
    r[...,6:]+=100;f[6:]=True
    b=run_mixture(r,lp,[5,20],t,f,'timing_informed',components=4)
    assert a[:6]==b[:6]

def test_identity_probabilities_match_exact_short_history_marginalization():
    residual=np.array([[[0.,3.,1.,60.,40.,15.],[1.,4.,2.,61.,41.,16.]],[[0.,5.,10.,15.,20.,25.],[2.,7.,12.,17.,22.,27.]]])
    lp=np.log([[.1,.3],[.4,.2]]);t=np.arange(6.);flags=np.array([0,0,1,0,0,0],bool)
    ev=np.array([[exact_evidence(r,[5,50],t,flags,'timing_informed') for r in candidate] for candidate in residual])+lp
    expected=np.exp(logsumexp(ev,axis=1)-logsumexp(ev))
    rows=run_mixture(residual,lp,[5,50],t,flags,'timing_informed',components=32)
    np.testing.assert_allclose(rows[-1]['identity_probabilities'],expected,atol=1e-8)

def test_offset_quadrature_does_not_use_post_warmup_values_in_proposal():
    from quality_offset_quadrature import offset_evidence
    r=np.array([0.,3.,1.,60.,40.,15.]);times=np.arange(6.);flags=np.zeros(6,bool)
    a=offset_evidence(r,[5,50],times,flags,'generic',nodes=32,warmup=3)
    r[4:]+=100;flags[4:]=True
    b=offset_evidence(r,[5,50],times,flags,'generic',nodes=32,warmup=3)
    np.testing.assert_array_equal(a[:4],b[:4])
