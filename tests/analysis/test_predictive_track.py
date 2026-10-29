import numpy as np
import pytest
from scipy.stats import multivariate_normal
from scipy.special import logsumexp
from leo.analysis.research.predictive_track import receiver_design,mixture_prediction,selected_predictive_coordinates


def test_receiver_design_agrees_with_existing_physical_geometry():
    from types import SimpleNamespace
    from ds23_predictive_linear import linear_geometry
    for fitted in (False,True):
        for receiver in (1,2):
            for channel in range(1,9):
                t=np.array([10.,100.,210.]);basis=np.array([[1.,0.],[.3,.7],[0.,1.]])
                rf=(10.7+.25*channel)*1e9
                track=dict(times=t,values=t*0,rf_hz=rf,receiver=receiver,channel=channel,observation_ids=['a','b','c'])
                scan=SimpleNamespace(tracks=[track],rx_basis=[basis],radio_sigma_hz=150.,fixed_window_noise=dict(
                    extra_parameter_BIC_gain=0,per_observation_noise_sigma_hz={}))
                p=SimpleNamespace(scan=scan,labels=[7],hardware=np.zeros((3,8+int(fitted))),smooth=np.zeros((3,4)),members=[],fitted_c=fitted)
                view,*_=linear_geometry(p,[dict(track_index=0,candidate_index=7,alias=0)])
                hardware=view.hardware.copy();hardware[:,[4,6]]*=10
                np.testing.assert_allclose(receiver_design(t,rf,receiver,channel,basis,fitted_c=fitted),np.c_[hardware,view.smooth*200])


def test_mixture_matches_joint_minus_training_evidence_and_keeps_inputs():
    y=np.array([1.,2.,3.]);means=np.array([[0.,1.,2.],[2.,2.,2.]])
    cov=np.array([np.eye(3)+.4,np.diag([1.,2.,3.])+.8]);logprior=np.log([.3,.7]);train=np.array([True,False,True]);held=~train
    originals=[v.copy() for v in [y,means,cov,logprior]]
    expected=-2*(logsumexp([lp+multivariate_normal.logpdf(y,mean=m,cov=c) for lp,m,c in zip(logprior,means,cov)])-
        logsumexp([lp+multivariate_normal.logpdf(y[train],mean=m[train],cov=c[np.ix_(train,train)]) for lp,m,c in zip(logprior,means,cov)]))
    result=mixture_prediction(y,means,cov,logprior,train,held)
    assert result['negative_twice_log_density']==pytest.approx(expected)
    for first,last in zip(originals,[y,means,cov,logprior]):np.testing.assert_array_equal(first,last)
    changed=y.copy();changed[held]+=10000
    altered=mixture_prediction(changed,means,cov,logprior,train,held)
    for key in ['held_mean_hz','held_covariance_hz2','training_mixture_weights']:
        np.testing.assert_array_equal(result[key],altered[key])
    assert altered['rms_hz']>result['rms_hz']+9900


def test_empty_training_is_prior_prediction_and_invalid_partitions_fail():
    y=np.array([1.,3.]);m=np.zeros((1,2));cov=np.eye(2)[None];train=np.zeros(2,bool);held=~train
    r=mixture_prediction(y,m,cov,np.zeros(1),train,held)
    assert r['negative_twice_log_density']==pytest.approx(-2*multivariate_normal.logpdf(y,mean=np.zeros(2),cov=np.eye(2)))
    with pytest.raises(ValueError,match='disjoint'):mixture_prediction(y,m,cov,np.zeros(1),held,held)


def test_selective_phase_moment_matches_gaussian_posterior_without_receiver_update():
    a=np.array([4.,2.]);cov=np.array([[3.,.2],[.2,2.]]);h=np.array([[1.,2.],[1.,3.],[1.,4.]])
    noise=np.eye(3)*2;r=np.array([5.,7.,9.])
    precision=np.linalg.inv(cov)+h.T@np.linalg.solve(noise,h)
    expected=np.linalg.solve(precision,h.T@np.linalg.solve(noise,r))
    before=(a.copy(),cov.copy())
    result=selected_predictive_coordinates(a,cov,h,r,noise,[1])
    assert result[0]==a[0]
    assert result[1]==pytest.approx(a[1]+expected[1])
    np.testing.assert_array_equal(a,before[0]);np.testing.assert_array_equal(cov,before[1])
