import numpy as np
import pytest
from scipy.special import logsumexp
from scipy.stats import multivariate_normal
from core import block_average,intercept_evidence,sample,assess


def test_integrated_constant_matches_covariance():
    r=np.array([1.,2.,4.]);sigma=2.;B=3.
    expected=multivariate_normal.logpdf(r,mean=np.zeros(3),cov=sigma**2*np.eye(3)+B**2*np.ones((3,3)))
    assert intercept_evidence(r,sigma,B)==pytest.approx(expected)


def test_blocks_use_only_partition():
    times=np.array([0.,.2,.5,1.1]);values=np.array([1.,3.,999.,5.]);mask=np.array([1,1,0,1],bool)
    assert np.array_equal(block_average(times,values,mask),[2.,5.])


def test_sampler_matches_small_exact_posterior_and_ignores_test():
    opts={'a':{'sat':{'train':np.array([[0.,-2.]]),'predict':np.zeros((1,2)),'n_test':1},
               '__null__':{'train':np.array([[-1.]]),'predict':np.zeros((1,1)),'n_test':1}}}
    priors={'sat':np.log([.5,.5])}
    states=sample(opts,priors,np.array([0.]),{'a':'sat'},seed=9,burn=10,draws=3000)
    lp=np.array([np.log(.9)+logsumexp(priors['sat']+opts['a']['sat']['train'][0]),np.log(.1)-1])
    exact=np.exp(lp-logsumexp(lp))[1]
    actual=np.mean([ids['a']=='__null__' for ids,c in states])
    assert abs(actual-exact)<.025
    opts['a']['sat']['predict'][:]=10000
    again=sample(opts,priors,np.array([0.]),{'a':'sat'},seed=9,burn=10,draws=3000)
    assert states==again


def test_shared_timing_does_not_independently_optimize_tracks():
    opts={t:{'sat':{'train':np.array([v]),'predict':np.array([[0.,-10.]]),'n_test':1}}
          for t,v in [('a',[0.,-100.]),('b',[-100.,0.])]}
    out=assess(opts,{'sat':np.log([.5,.5])},[({'a':'sat','b':'sat'},0)])
    assert out['tracks'][0]['predictive_log_score']==pytest.approx(np.log(.5+.5*np.exp(-10)))
