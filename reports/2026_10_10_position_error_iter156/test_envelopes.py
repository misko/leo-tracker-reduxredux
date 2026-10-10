"""Prepared synthetic checks only; no recording/integration experiment."""
import math

import numpy as np
import pytest
from scipy.special import ndtr

from envelopes import cell_envelope, curvature_bounds, log_affine_integral, seam_log_bound


def curvature(a, measured, d, amplitudes, clutter, sigma, precision):
    residual=measured-d*a
    signal=amplitudes*np.exp(-.5*(residual/sigma)**2)
    w=signal/(clutter+signal.sum())
    return -precision+d*d*((w*residual**2).sum()/sigma**4
                           -(w*residual).sum()**2/sigma**4-w.sum()/sigma**2)


def test_finite_gaussian_clutter_observed_curvature_bound():
    sigma,lam,d,b=1.3,.07,1.7,.02
    peaks=np.array([.3,.9,1.2]);means=np.array([-4.,.3,8.])
    h,u=curvature_bounds([d],[peaks.sum()/b],sigma,lam)
    for a in np.linspace(-20,20,121):
        actual=curvature(a,means,d,peaks,b,sigma,lam)
        assert -h-1e-12 <= actual <= u+1e-12
    assert curvature_bounds([9.],[0.],sigma,lam)==(lam,-lam)


@pytest.mark.parametrize('gradient',[0.,1e-10,-3.,1000.])
def test_affine_integral_and_envelope(gradient):
    value,h=2.,.3
    actual=log_affine_integral(value,gradient,h)
    if abs(gradient)<1e-8: assert actual==pytest.approx(value+math.log(2*h),abs=1e-10,rel=0)
    elif gradient==-3: assert actual==pytest.approx(value+math.log((math.exp(gradient*h)-math.exp(-gradient*h))/gradient),abs=1e-12,rel=0)
    bound=cell_envelope(value,gradient,h,0.,0.,seam_log_total=-math.inf)
    assert bound['log_lower']<=actual<=bound['log_upper']


def test_gaussian_integral_and_units_scaling():
    lam,mu,h=.8,.4,2.
    value,gradient=-.5*lam*mu*mu,lam*mu
    exact=.5*math.log(2*math.pi/lam)+math.log(ndtr(math.sqrt(lam)*(h-mu))-ndtr(math.sqrt(lam)*(-h-mu)))
    bound=cell_envelope(value,gradient,h,lam,-lam,seam_log_total=-math.inf)
    assert bound['log_lower']<=exact<=bound['log_upper']
    scale=100.
    other=cell_envelope(value,gradient*scale,h/scale,lam*scale**2,-lam*scale**2,seam_log_total=-math.inf)
    assert other['log_affine']+math.log(scale)==pytest.approx(bound['log_affine'],abs=1e-12,rel=0)
    h1,u1=curvature_bounds([2.],[30.],1.,lam)
    h2,u2=curvature_bounds([2.*scale],[30.],1.,lam*scale**2)
    assert h2==pytest.approx(h1*scale**2) and u2==pytest.approx(u1*scale**2)


def test_remote_narrow_mode_upper_not_midpoint_assumption():
    # exp(L)=clutter + narrow remote Gaussian; flat midpoint badly undercounts.
    sigma,peak,clutter,center,h=.05,100.,.01,3.,5.
    residual=center
    signal=peak*math.exp(-.5*(residual/sigma)**2)
    value=math.log(clutter+signal)
    gradient=signal/(clutter+signal)*residual/sigma**2
    hb,ub=curvature_bounds([1.],[peak/clutter],sigma,1e-12)
    # Add the tiny proper prior exactly at midpoint; bound its Gaussian factor
    # below on this finite interval when deriving the independent integral lower.
    bound=cell_envelope(value,gradient,h,hb,ub,seam_log_total=-math.inf)
    density_integral=2*h*clutter+peak*sigma*math.sqrt(2*math.pi)*(ndtr((h-center)/sigma)-ndtr((-h-center)/sigma))
    log_lower_exact=math.log(density_integral)-.5e-12*h*h
    log_upper_exact=math.log(density_integral)
    assert log_lower_exact>value+math.log(2*h)+1
    assert bound['log_lower']<=log_lower_exact and bound['log_upper']>=log_upper_exact


def test_tiny_seam_jump_not_silently_declared_zero():
    logj=seam_log_bound([1.],[100.],125.,227272.,1.)
    assert math.isfinite(logj) and logj < -1000
    bound=cell_envelope(0.,0.,1.,1.,1.,seam_log_total=logj)
    assert bound['seam_remainder_underflow'] and math.isfinite(bound['seam_log_remainder'])
    assert bound['log_upper']>math.log(2)+.5
    assert seam_log_bound([0.],[100.],125.,227272.,1.)==-math.inf


@pytest.mark.parametrize('direction', [-7., 7.])
def test_multicomponent_multiple_winding_jump_sum(direction):
    period, sigma, h, clutter = 4., 1., 3., .2
    means = np.array([.1, .8, 1.6])
    peaks = np.array([.3, .9, 1.2])
    jump_sum = 0.
    crossings = 0
    for j, mean in enumerate(means):
        for winding in range(-20, 21):
            a = (mean-(winding+.5)*period)/direction
            if -h < a < h:
                residual = (means-direction*a+period/2) % period-period/2
                density = clutter + np.sum(peaks*np.exp(-.5*(residual/sigma)**2))
                jump_sum += abs(direction)*period*peaks[j]*math.exp(-period**2/(8*sigma**2))/(sigma**2*density)
                crossings += 1
    assert crossings > 3  # Multiple windings, rather than a row-crosses boolean.
    log_bound = seam_log_bound([direction], [peaks.sum()/clutter], sigma, period, h)
    assert 0 < jump_sum <= math.exp(log_bound)


@pytest.mark.parametrize('seam',[-.3,.3])
def test_upward_seam_on_either_side_of_anchor(seam):
    # L(x)=|x-seam|, smooth curvature zero, derivative jump exactly two.
    h=1.;value=abs(seam);gradient=-1. if seam>0 else 1.
    exact=math.log(2*math.exp(h)*math.cosh(seam)-2)
    bound=cell_envelope(value,gradient,h,0.,0.,seam_log_total=math.log(2))
    assert bound['log_lower']<=exact<=bound['log_upper']


@pytest.mark.parametrize('call',[
    lambda:curvature_bounds([1.],[-1.],1.,1.),
    lambda:curvature_bounds([float('nan')],[1.],1.,1.),
    lambda:curvature_bounds([1.],[1.],0.,1.),
    lambda:log_affine_integral(0.,0.,0.),
    lambda:cell_envelope(0.,0.,1.,1.,-2.,seam_log_total=-math.inf),
    lambda:cell_envelope(0.,0.,1.,1.,1.,seam_log_total=math.nan),
    lambda:seam_log_bound([1.],[1.],1.,math.inf,1.),
])
def test_invalid_domains_rejected(call):
    with pytest.raises(ValueError):call()
