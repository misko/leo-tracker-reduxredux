from pathlib import Path
import sys
import numpy as np
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools'))
from ds23_channel_clock_screen import ramp,fit,prediction,predictive_score,select,transfer


def test_fractional_UTC_phase_is_preserved_and_periodic():
    origin=1791989274888016232;t=np.array([0.,1.,100.])
    np.testing.assert_allclose(ramp(t,origin,1.5),ramp(t+15,origin,1.5),atol=1e-14)
    expected=((origin%15_000_000_000)/1e9-1.5)%15/15-.5
    assert abs(ramp(t,origin,1.5)[0]-expected)<1e-15


def test_common_ramp_predicts_the_other_receiver_without_learning_its_amplitude():
    rng=np.random.default_rng(2);t=np.arange(0.,150.,.73);g=ramp(t,0,2.5)
    first=20000+12*t+.1*t*t+700*g+rng.normal(0,15,len(t))
    second=-10000+15*t+.1*t*t+700*g+rng.normal(0,15,len(t))
    test=(np.floor(t/15).astype(int)%3)==1;train=~test
    best,null=select(t[train],first[train],40.,0)
    assert best['selected_over_baseline']
    assert best['phase_s']==2.5
    alternative=transfer(best,t[train],second[train]);baseline=fit(t[train],second[train],40.,0)
    a,c=prediction(alternative,t[test]);b,d=prediction(baseline,t[test])
    assert predictive_score(a,c,second[test])<predictive_score(b,d,second[test])-50
    assert alternative['amplitude_peak_to_peak_hz']==best['amplitude_peak_to_peak_hz']


def test_receiver_specific_ramp_does_not_predict_a_clean_other_receiver():
    t=np.arange(0.,150.,.73);test=(np.floor(t/15).astype(int)%3)==1;train=~test
    source=fit(t[train],700*ramp(t[train],0,2.5),40.,0,phase_s=2.5)
    clean=3*t+.01*t*t
    transferred=transfer(source,t[train],clean[train]);baseline=fit(t[train],clean[train],40.,0)
    a,c=prediction(transferred,t[test]);b,d=prediction(baseline,t[test])
    assert predictive_score(a,c,clean[test])>predictive_score(b,d,clean[test])+50


def test_a_smooth_polynomial_does_not_select_a_reset_clock():
    t=np.arange(60.);y=100+3*t+t*t+.0001*t**4
    best,_=select(t,y,40.,0)
    assert not best['selected_over_baseline']


def test_clock_amplitude_uncertainty_is_integrated_into_held_prediction():
    t=np.linspace(0,80,70);model=fit(t,np.sin(t),100.,0,phase_s=1.)
    _,a=prediction(model,np.array([5.,10.]));fixed=dict(model,amplitude_variance_hz2=0.)
    _,b=prediction(fixed,np.array([5.,10.]))
    assert np.linalg.eigvalsh(a-b).min()>-1e-9
    assert np.trace(a-b)>0


def test_training_and_prediction_errors_are_explicit():
    with pytest.raises(ValueError):fit(np.arange(9.),np.arange(9.),40.,0)
    with pytest.raises(ValueError):ramp(np.array([np.nan]),0,0.)
    with pytest.raises(ValueError):predictive_score(np.zeros(2),np.eye(3),np.zeros(2))


def test_predictive_moments_equal_direct_joint_polynomial_ramp_integration():
    rng=np.random.default_rng(31);t=np.arange(0.,90.,.8);test=np.array([3.,17.,42.,71.])
    y=5*t+400*ramp(t,0,2.)+rng.normal(0,20,len(t));model=fit(t,y,40.,0,phase_s=2.)
    v=np.polynomial.legendre.legvander((t-model['center_s'])/model['scale_s'],4)
    u=np.column_stack((v,ramp(t,0,2.)))
    prior=np.diag([0.]*5+[1/300.**2]);normal=u.T@u/40.**2+prior
    covariance=np.linalg.inv(normal);coefficient=np.linalg.solve(normal,u.T@y/40.**2)
    vt=np.polynomial.legendre.legvander((test-model['center_s'])/model['scale_s'],4)
    ut=np.column_stack((vt,ramp(test,0,2.)));a,c=prediction(model,test)
    np.testing.assert_allclose(a,ut@coefficient,rtol=0,atol=1e-8)
    np.testing.assert_allclose(c,np.eye(len(test))*40.**2+ut@covariance@ut.T,rtol=0,atol=1e-7)


def test_transfer_retains_target_noise_and_source_amplitude_uncertainty():
    t=np.arange(60.);source=fit(t,300*ramp(t,0,2.),40.,0,phase_s=2.)
    target=transfer(source,t,np.sin(t),sigma_hz=150.)
    assert target['sigma_hz']==150.
    assert target['amplitude_variance_hz2']==source['amplitude_variance_hz2']
