import numpy as np
import pytest
from leo.analysis.research.cut_receiver_prediction import cut_receiver_prediction
from leo.analysis.research.predictive_track import mixture_prediction


def test_receiver_only_training_cannot_move_held_mean_or_reduce_uncertainty():
    y=np.array([10.,2.,3.]);mean=np.zeros((1,3));frozen=np.ones((3,3))*100
    covariance=(np.eye(3)+frozen)[None];train=np.array([True,False,False]);held=~train
    before=[a.copy() for a in (y,mean,covariance,frozen)]
    result=cut_receiver_prediction(y,mean,covariance,frozen,[0.],train,held)
    np.testing.assert_allclose(result['held_mean_hz'],0)
    np.testing.assert_allclose(result['held_covariance_hz2'],np.eye(2)+100)
    ordinary=mixture_prediction(y,mean,covariance,[0.],train,held)
    assert ordinary['held_mean_hz'][0]>9
    for a,b in zip(before,(y,mean,covariance,frozen)):np.testing.assert_array_equal(a,b)


def test_zero_receiver_uncertainty_equals_ordinary_conditioning_and_held_values_do_not_leak():
    y=np.array([2.,4.,-1.]);means=np.array([[0.,0.,0.],[1.,2.,1.]])
    cov=np.array([np.eye(3)+2,np.eye(3)*3+1]);frozen=np.zeros((3,3));train=np.array([True,False,True]);held=~train
    cut=cut_receiver_prediction(y,means,cov,frozen,np.log([.3,.7]),train,held)
    ordinary=mixture_prediction(y,means,cov,np.log([.3,.7]),train,held)
    for key in ('negative_twice_log_density','held_mean_hz','held_covariance_hz2','training_mixture_weights'):
        np.testing.assert_allclose(cut[key],ordinary[key])
    altered=y.copy();altered[held]+=1000
    other=cut_receiver_prediction(altered,means,cov,frozen,np.log([.3,.7]),train,held)
    for key in ('held_mean_hz','held_covariance_hz2','training_mixture_weights'):
        np.testing.assert_array_equal(cut[key],other[key])


def test_cut_matches_explicit_latent_conditional_integration():
    # Scalar satellite a and scalar receiver beta: independently derive the
    # held distribution by integrating beta without its target update.
    h=np.array([1.,2.,4.]);u=np.array([2.,1.,3.]);noise=2.;sa=3.;sb=5.
    frozen=sb*np.outer(h,h);total=noise*np.eye(3)+sa*np.outer(u,u)+frozen
    train=np.array([True,False,False]);held=~train;y=np.array([7.,2.,3.])
    r=cut_receiver_prediction(y,np.zeros((1,3)),total[None],frozen,[0.],train,held)
    var_a=1/(1/sa+u[0]**2/noise);g=var_a*u[0]/noise
    expected_mean=u[held]*g*y[0]
    effective_h=h[held]-u[held]*g*h[0]
    expected_cov=noise*np.eye(2)+var_a*np.outer(u[held],u[held])+sb*np.outer(effective_h,effective_h)
    np.testing.assert_allclose(r['held_mean_hz'],expected_mean)
    np.testing.assert_allclose(r['held_covariance_hz2'],expected_cov)
    with pytest.raises(ValueError,match='disjoint'):
        cut_receiver_prediction(y,np.zeros((1,3)),total[None],frozen,[0.],held,held)


def test_conditional_identity_score_can_discard_training_incompatibility():
    y=np.array([10.,0.]);cov=np.eye(2)[None];train=np.array([True,False]);held=~train
    scores=[]
    for mean in (np.array([[10.,0.]]),np.array([[0.,0.]])):
        conditional=mixture_prediction(y,mean,cov,[0.],train,held)
        joint=mixture_prediction(y,mean,cov,[0.],np.zeros(2,bool),np.ones(2,bool))
        assert joint['negative_twice_log_density']==pytest.approx(
            conditional['negative_twice_log_density']+conditional['training_negative_twice_log_density'])
        scores.append((conditional['negative_twice_log_density'],joint['negative_twice_log_density']))
    assert scores[0][0]==pytest.approx(scores[1][0])
    assert scores[1][1]-scores[0][1]==pytest.approx(100.)


def test_invalid_frozen_covariance_is_rejected():
    with pytest.raises(ValueError,match='positive semidefinite'):
        cut_receiver_prediction([0.,0.],np.zeros((1,2)),np.eye(2)[None],-np.eye(2),
                                [0.],[True,False],[False,True])
