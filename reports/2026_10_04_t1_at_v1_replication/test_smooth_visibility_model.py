from types import SimpleNamespace

import numpy as np
import pytest

import position_visibility_study as s
from smooth_visibility_model import (GATES,finite_set_terms,gate_terms,horizon_geometry,observer_pose)
from prediction_jacobian import paired_prediction_jacobian
from test_position_structure_study import data as small_data


@pytest.mark.parametrize('gate',GATES)
def test_gate_bounds_and_monotonicity(gate):
    x=np.linspace(-1,1,10001);w,g=gate_terms(x,gate)
    assert np.all(w>=0) and np.all(w<=1) and np.all(g>=0)
    assert np.min(np.diff(w))>=-1e-14


@pytest.mark.parametrize('gate',['L1','L4','P1','Q1'])
def test_gate_gradient_and_saturation(gate):
    x=np.sin(np.deg2rad(np.array([-3,-.2,0.,.1,.5,.9,1.,2.,10.])))
    w,g=gate_terms(x,gate);h=1e-7
    num=(gate_terms(x+h,gate)[0]-gate_terms(x-h,gate)[0])/(2*h)
    np.testing.assert_allclose(g,num,atol=2e-7,rtol=1e-6)
    if gate=='Q1':
        assert np.all(w[x<=0]==0) and np.all(g[x<=0]==0)
        assert np.all(w[x>=np.sin(np.deg2rad(1.))]==1)


@pytest.mark.parametrize('gate',['L1','L4','P1'])
def test_centered_transition_width(gate):
    half=GATES[gate]['width_deg']/2
    w,_=gate_terms(np.sin(np.deg2rad([-half,0,half])),gate)
    np.testing.assert_allclose(w,[.1,.5,.9],atol=1e-13)


def test_hard_probabilities_match_old_finite_set_score_and_gradient():
    d=small_data();pred=np.column_stack([d.measured+50.,d.measured+100000.])
    visible=np.array([[1,1],[1,0],[0,1],[0,0],[1,1],[1,1]],bool)
    for weighting in ('C1','A03'):
        w=s.old.row_weights(d,weighting);q=.8/2*visible
        a=finite_set_terms(d.measured,pred,q,w)
        old=s.old.SingleWindowLikelihood(d,np.zeros((6,1)),weighting)
        b=old.evaluate(pred,visible,sigma_hz=200.)
        for key in ('total_log_likelihood','prediction_gradient','row_association_probability','irls_weights'):
            np.testing.assert_allclose(a[key],b[key],atol=1e-12,rtol=1e-10)


@pytest.mark.parametrize('gate',['L1','L4','P1','Q1'])
def test_full_likelihood_elevation_gradient_including_normalizer(gate):
    d=small_data();pred=np.column_stack([d.measured+90.,d.measured+65000.])
    sine=np.sin(np.deg2rad(np.column_stack([np.linspace(-.2,1.,6),np.linspace(-.1,.7,6)])))
    weights=s.old.row_weights(d,'A03');w,dw=gate_terms(sine,gate)
    a=finite_set_terms(d.measured,pred,.4*w,weights)
    grad=a['probability_gradient']*.4*dw
    for i,j in [(0,0),(2,1),(3,0),(5,1)]:
        eps=1e-7;l,r=sine.copy(),sine.copy();l[i,j]-=eps;r[i,j]+=eps
        num=(finite_set_terms(d.measured,pred,.4*gate_terms(r,gate)[0],weights)['total_log_likelihood']-
             finite_set_terms(d.measured,pred,.4*gate_terms(l,gate)[0],weights)['total_log_likelihood'])/(2*eps)
        assert num==pytest.approx(grad[i,j],abs=1e-6,rel=1e-6)
    np.testing.assert_allclose(a['row_association_probability'].sum(axis=1)+a['row_clutter_probability'],1.)


def synthetic_geometry():
    nodes=np.arange(-2.,5.)
    obs,up=observer_pose(np.zeros(2),s.FRAME)
    tangent=np.cross(up,[0.,0.,1.]);tangent/=np.linalg.norm(tangent)
    origin=np.stack([obs+2000*tangent+100*up,obs-1800*tangent-20*up])
    velocity=np.stack([-2*tangent+3*up,2*tangent+1*up])
    positions=origin[:,None,:]+nodes[None,:,None]*velocity[:,None,:]
    return SimpleNamespace(numbers=np.array([10,20]),nodes=nodes,position=positions,
        velocity=np.broadcast_to(velocity[:,None,:],positions.shape).copy(),
        times=np.array([.4,1.2]),rf=np.array([11e9,11.5e9]),receiver=np.array([0,1]))


def test_geometry_visibility_matches_original_predictor_and_jacobian():
    d=synthetic_geometry();v=np.array([.2,-.3,0.,0.,0.,0.,.1,-.2])
    sine,jac=horizon_geometry(d,v,s.FRAME)
    _,visible,_=paired_prediction_jacobian(d,v,np.repeat(np.arange(2),2),np.tile(np.arange(2),2))
    np.testing.assert_array_equal(sine.ravel()>=0,visible)
    dense=jac.to_dense()
    for i in (0,1,6,7):
        eps=1e-4;l,r=v.copy(),v.copy();l[i]-=eps;r[i]+=eps
        numerical=(horizon_geometry(d,r,s.FRAME)[0]-horizon_geometry(d,l,s.FRAME)[0])/(2*eps)
        np.testing.assert_allclose(numerical.ravel(),dense[:,i],atol=2e-10,rtol=1e-5)
    h=jac.normal_matrix(np.ones(4));assert np.linalg.eigvalsh(h).min()>-1e-12


def test_q_validation():
    for q in (-.1,1.,np.nan):
        with pytest.raises(ValueError):finite_set_terms([0.],np.zeros((1,1)),np.array([[q]]),np.ones(1))


def test_experiment_factorial():
    assert len(s.GATES)==5 and len(s.ARMS)==2 and len(s.WEIGHTS)==2 and len(s.SCANS)==16
    assert len({s.name(scan,a,g,w) for scan in s.SCANS for a in s.ARMS for g in s.GATES for w in s.WEIGHTS})==320
