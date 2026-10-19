"""Importance normalization against analytic and quadrature evidence."""

import sys
import math
from pathlib import Path
import numpy as np
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools'))
from probe_ds23_marginal_evidence import gaussian_integral,integrate


def test_fractional_power_gaussian_integral_matches_direct_quadrature():
    y=np.array([.2,1.,-.4]);u=np.array([[1.],[.5],[-.7]]);s=np.ones(3)
    groups=np.array([0,0,1]);power=np.array([.3,.8]);tau=np.array([1.2,.7]);precision=np.array([2.])
    analytic=gaussian_integral(y,u,s,groups,power,tau,precision)
    a=np.linspace(-8,8,40001);r=y[:,None]-u*a
    logp=-.5*np.sum(power[groups,None]*(np.log(2*np.pi)-np.log(tau[groups,None])+tau[groups,None]*r*r),axis=0)
    logp+=.5*np.log(precision[0]/(2*np.pi))-.5*precision[0]*a*a
    maximum=logp.max();quadrature=-2*(maximum+np.log(np.trapezoid(np.exp(logp-maximum),a)))
    assert analytic==pytest.approx(quadrature,abs=1e-9)


def test_exact_noise_gamma_proposal_has_constant_weights_and_matches_student_integral():
    y=np.array([.2,1.,-.4]);groups=np.zeros(3,int);power=np.array([.6]);sigma=np.ones(3)
    a0=b0=2.;shape=a0+power[0]*len(y)/2;rate=b0+power[0]*(y@y)/2
    result=integrate(y,np.empty((3,0)),sigma,groups,power,np.array([shape/rate]),np.array([],int),np.empty(0),None,samples=64)
    logp=-.5*power[0]*len(y)*np.log(2*np.pi)+a0*np.log(b0)-math.lgamma(a0)+math.lgamma(shape)-shape*np.log(rate)
    assert result['negative_twice_log_evidence']==pytest.approx(-2*logp)
    assert result['effective_samples']==pytest.approx(64)
    assert result['Monte_Carlo_SE']<1e-12
