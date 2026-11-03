from math import erf,sqrt,log,pi
from types import SimpleNamespace
import numpy as np
import pytest

import ds23_marginal_clock as clock
from leo.analysis.research.continuous_curve_fit import paired_phase_frequency
from ds23_height_problem import geometry_features
from ds23_bracketed_clock import clock_geometry as old_phase_clock_geometry


def test_uniform_quadrature_is_normalized_even_for_asymmetric_interval():
    nodes,w=clock.uniform_quadrature(-.125,.07,15)
    assert w.sum()==pytest.approx(1.)
    assert w@nodes==pytest.approx((-.125+.07)/2)
    assert w@((nodes-w@nodes)**2)==pytest.approx((.195)**2/12)


def test_quadrature_matches_exact_gaussian_integral():
    a,b,y,sigma=-.2,.1,.065,.035
    nodes,w=clock.uniform_quadrature(a,b,31)
    result=clock.mixture(((nodes-y)/sigma)**2+log(2*pi*sigma*sigma),w)
    probability=.5*(erf((b-y)/(sigma*sqrt(2)))-erf((a-y)/(sigma*sqrt(2))))/(b-a)
    assert result['objective']==pytest.approx(-2*log(probability),abs=1e-10)


def test_mixture_residual_exact_objective_and_degenerate_identity():
    r=[np.array([3.,-2.]),np.array([1.,4.])];w=[.2,.8]
    m=clock.mixture_residual(r,w)
    expected=-2*np.log(.2*np.exp(-13/2)+.8*np.exp(-17/2))
    assert m['residual']@m['residual']==pytest.approx(expected)
    one=clock.mixture_residual([r[0]],[1.])
    np.testing.assert_array_equal(one['residual'][:-1],r[0]);assert one['residual'][-1]==0


def test_clock_uncertainty_is_retained_in_prediction():
    c=np.array([1.,2.,3.]);l=np.array([0.,6.,20.]);w=np.ones(3)/3
    curv=clock.mixture(c,w);joint=clock.mixture(c+l,w)
    conditional=-2*np.log(np.sum(curv['weights']*np.exp(-l/2)))
    assert joint['objective']-curv['objective']==pytest.approx(conditional)
    assert abs(conditional-l[np.argmax(curv['weights'])])>.1


def test_reported_clock_mode_uses_curved_data_even_when_linear_prefers_other_node():
    class Node:
        keep=np.array([True]);lower=np.array([-1.,-1.]);upper=np.array([1.,1.])
        def __init__(self,curved,linear,coefficient):
            self.curved,self.linear,self.coefficient=curved,linear,coefficient
        def calculate(self,x):
            return dict(negative_twice_elbo=self.curved+self.linear,
                curved_negative_twice_elbo=self.curved,elevation=np.array([30.]),
                coefficient=np.array([self.coefficient]),conditional_residual_hz=np.array([0.]))
        def residual(self,x):return np.array([sqrt(self.curved+self.linear)])
    result=clock.MarginalClock([Node(1.,20.,7.),Node(2.,0.,99.)],[.5,.5]).calculate([0.,0.])
    assert result['curved_clock_mode']==0
    assert result['joint_clock_weights'][1]>.99
    assert result['coefficient'][0]==7.


def toy_geometry():
    t=np.arange(-3.,13.);angle=.0011*t;earth=7.292115e-5*t
    inertial=np.column_stack((7000*np.cos(angle),5000*np.sin(angle),4900*np.sin(angle)))
    velocity=np.column_stack((-7.7*np.sin(angle),5.5*np.cos(angle),5.39*np.cos(angle)))
    r=inertial.copy();v=velocity.copy()
    for values,source in ((r,inertial),(v,velocity)):
        values[:,0]=np.cos(earth)*source[:,0]+np.sin(earth)*source[:,1]
        values[:,1]=-np.sin(earth)*source[:,0]+np.cos(earth)*source[:,1]
    v-=np.cross(np.array([0.,0.,7.292115e-5]),r)
    bank=dict(time_s=t,position_km=r[None],velocity_km_s=v[None])
    modes=dict(time_s=t,position_km=np.zeros((3,len(t),3)),velocity_km_s=np.zeros((3,len(t),3)))
    return SimpleNamespace(variant='normal',sky=bank,mode_bank=modes,reference=np.array([.2]),
        flat_times=np.array([2.,4.,6.]),flat_labels=np.zeros(3,int),q=np.ones(3),phase_sigma=np.array([.1]),
        labels=[0],supported=[],supported_local=[],hardware=np.zeros((3,8)),smooth=np.zeros((3,2)),constants=np.zeros((3,1)))


def test_UTC_advances_observation_time_without_undoing_earth_rotation():
    from prototype_dsx01_continuous_position import latlon
    p=toy_geometry();shift=.1
    actual=clock.utc_geometry(p,[0.,0.],shift)
    expected=paired_phase_frequency(p.sky,p.flat_times+shift,p.flat_labels,p.reference,*latlon([0.,0.]))[0]
    np.testing.assert_allclose(actual['frequency'],expected,atol=1e-9)
    wrong=old_phase_clock_geometry(p,[0.,0.],shift)['frequency']
    assert max(abs(wrong-expected))>1e-3
    np.testing.assert_array_equal(p.flat_times,[2.,4.,6.])
    np.testing.assert_array_equal(p.reference,[.2])


def test_zero_clock_geometry_is_original_geometry():
    p=toy_geometry();original=geometry_features(p,[0.,0.],0.)
    zero=clock.utc_geometry(p,[0.,0.],0.)
    for key in ('features','intercept','frequency','elevation'):
        np.testing.assert_array_equal(zero[key],original[key])
