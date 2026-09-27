import numpy as np
from itertools import product
from scipy.special import logsumexp
from causal_quality import run_filter
from catalogue_trial import constant_log_evidence

def test_stationary_filter_matches_exact_marginal_likelihood():
    rng=np.random.default_rng(82);r=rng.normal(size=(2,3,15))*30+200000
    prior=np.full((2,3),-np.log(6));scales=np.array([5.,20.,100.]);times=np.arange(15.)
    rows=run_filter(r,prior,scales,times,np.zeros(15,bool),warmup=5)
    full=logsumexp(np.stack([constant_log_evidence(r,s) for s in scales])+prior)-np.log(3)
    prefix=logsumexp(np.stack([constant_log_evidence(r[...,:5],s) for s in scales])+prior)-np.log(3)
    assert np.isclose(sum(x['log_predictive'] for x in rows),full,atol=1e-7)
    assert np.isclose(sum(x['log_predictive'] for x in rows if x['held']),full-prefix,atol=1e-7)

def test_future_values_and_flags_cannot_change_past_predictions():
    rng=np.random.default_rng(83);r=rng.normal(size=(2,3,15))*20;prior=np.full((2,3),-np.log(6));flags=np.zeros(15,bool);flags[7]=True;times=np.arange(15.)
    a=run_filter(r,prior,[5,20,100],times,flags,'timing_informed')
    r[...,10:]+=1000;flags[10:]=True
    b=run_filter(r,prior,[5,20,100],times,flags,'timing_informed')
    assert a[:10]==b[:10]
    generic=run_filter(r,prior,[5,20,100],times,np.zeros(15,bool),'generic')
    assert a[:8]==generic[:8]
    assert a[8]['transition_probability']>generic[8]['transition_probability']

def test_unflagged_timing_model_equals_generic():
    r=np.array([[[1.,2.,4.,3.]]]);prior=np.zeros((1,1));times=np.arange(4.);flags=np.zeros(4,bool)
    assert run_filter(r,prior,[5,20],times,flags,'generic')==run_filter(r,prior,[5,20],times,flags,'timing_informed')

def test_exact_history_oracle_agrees_with_independent_path_sum():
    from causal_quality_accuracy import exact_evidence
    residual=np.array([0.,3.,1.,60.,40.,15.]);scales=np.array([5.,50.]);times=np.arange(6.);flags=np.zeros(6,bool);flags[2]=True
    paths=[]
    for states in product(range(2),repeat=6):
        logp=-np.log(2)
        for i in range(1,6):
            h=-np.expm1(-1/20)
            if flags[i-1]:h=1-(1-h)*.5
            logp+=np.log(h/2+(1-h)*(states[i]==states[i-1]))
        variance=scales[list(states)]**2;w=1/variance;W=w.sum();mean=w@residual/W
        ll=-.5*(6*np.log(2*np.pi)+np.log(variance).sum()+np.log1p(1e12*W)+np.sum(w*(residual-mean)**2)+mean**2/(1e12+1/W))
        paths.append(logp+ll)
    exact=logsumexp(paths)
    assert np.isclose(exact_evidence(residual,scales,times,flags,'timing_informed'),exact,atol=1e-12)
    stationary=logsumexp([constant_log_evidence(residual,s) for s in scales])-np.log(len(scales))
    assert np.isclose(exact_evidence(residual,scales,times,flags,'stationary'),stationary,atol=1e-12)
