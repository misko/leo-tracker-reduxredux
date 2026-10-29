"""Scalar dense oracle for the batched new-family likelihood."""
from types import SimpleNamespace
import numpy as np
import pytest
from scipy.special import logsumexp
import predictive_new_family as module
from leo.analysis.research.continuous_curve_fit import paired_phase_frequency
from leo.analysis.research.orbit_uncertainty import paired_frequency_modes
from leo.analysis.research.predictive_track import gaussian_log_density,receiver_design
from leo.sky.frames import geodetic_to_ecef_km


def test_joint_two_track_family_matches_dense_phase_oracle_and_preserves_calibration(monkeypatch):
    rng=np.random.default_rng(827);knots=np.arange(-20.,321.,5);coordinates=module.latlon([0.,0.])
    site=geodetic_to_ecef_km(*coordinates,0.);up=site/np.linalg.norm(site)
    position=site+up*600+(knots[:,None]-150)*[0.,2.,0.]
    bank=dict(time_s=knots,position_km=position[None],velocity_km_s=np.broadcast_to([0.,2.,0.],(1,len(knots),3)))
    dp=np.broadcast_to(np.eye(3)[:,None,:]*.1,(3,len(knots),3));dv=dp*.001
    modes=dict(time_s=knots,position_km=dp,velocity_km_s=dv)
    monkeypatch.setattr(module,'build_modes',lambda *a:(modes,{}))
    monkeypatch.setattr(module,'phase_widths',lambda *a:(np.array([8.]),{}))
    monkeypatch.setattr(module,'forecast_phase_mean',lambda *a:np.array([0.]))
    tracks=[];basis=[];entries=[]
    for i,(rx,ch) in enumerate([(1,7),(2,8)]):
        t=np.linspace(60+40*i,130+40*i,8);rf=12e9+ch*1e6
        f,_=paired_phase_frequency(bank,t,np.zeros(8,int),np.array([2.]),*coordinates)
        tracks.append(dict(key=str(i),times=t,values=rf/11.5e9*f+rng.normal(0,20,8),rf_hz=rf,receiver=rx,channel=ch,
                           observation_ids=[f'{i}-{k}' for k in range(8)]));basis.append(np.ones((8,1)))
        entries.append(dict(track_index=i,candidate_index=0,norad=42,alias=0,points=8,component=str(i),observation_ids=tracks[-1]['observation_ids']))
    scan=SimpleNamespace(tracks=tracks,rx_basis=basis,sky=bank,norads=np.array([42]),radio_sigma_hz=150.,
                         fixed_window_noise=dict(extra_parameter_BIC_gain=0,per_observation_noise_sigma_hz={}))
    family=module.NewFamily(scan,entries,dict(shrinkage=0,multiplier=1,nu=None),phase_step=15.)
    features=rng.normal(size=(17,10));coef=rng.normal(size=10)*.001
    calculated=dict(coefficient=coef,features=features,noise_precision=np.ones(1),coefficient_prior_precision=np.ones(10))
    p=SimpleNamespace(labels=[1],fitted_c=False,keep=np.ones(17,bool),noise_groups=np.zeros(17,int),point_noise=np.full(17,150.),calculate=lambda x:calculated)
    before=coef.copy();actual=family.evaluate(p,np.zeros(2),np.ones(1),[])
    h=np.concatenate([receiver_design(t['times'],t['rf_hz'],t['receiver'],t['channel'],b) for t,b in zip(tracks,basis,strict=True)])
    covariance=np.linalg.inv(np.eye(10)+features.T@features/150**2);density=[]
    for phase in family.phases:
        f,e=paired_phase_frequency(bank,family.times,np.zeros(16,int),np.array([phase]),*coordinates)
        u=paired_frequency_modes(bank,modes,family.times,np.zeros(16,int),np.array([phase]),*coordinates)*family.q[:,None]
        density.append(gaussian_log_density(family.values-h@coef-family.q*f,family.noise+h@covariance@h.T+u@u.T) if e.min()>=0 else -np.inf)
    expected=-2*logsumexp(family.logprior-logsumexp(family.logprior)+density)
    assert actual==pytest.approx(expected,rel=1e-10)
    np.testing.assert_array_equal(coef,before)
    p.labels=[0,1];p.rows=[dict(candidate_index=1)];p.slices=[slice(0,17)]
    with pytest.raises(ValueError,match='disabled'):family.evaluate(p,np.zeros(2),np.ones(1),[])
    family.allow_uncalibrated_label=True
    assert family.evaluate(p,np.zeros(2),np.ones(1),[])==pytest.approx(actual)
    p.rows=[dict(candidate_index=0)]
    with pytest.raises(ValueError,match='active calibration'):family.evaluate(p,np.zeros(2),np.ones(1),[])
    p.labels=[1]
    with pytest.raises(ValueError,match='conditioning'):family.evaluate(p,np.zeros(2),np.ones(1),[dict(candidate_index=0)])
