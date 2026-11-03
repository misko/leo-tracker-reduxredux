"""Guard physical prior means and Gaussian fallback in the calibrated model."""

import copy
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools'))
import probe_ds23_history_calibrated_phase as learned
import probe_ds23_weighted_priors as controls


def fake_problem(*args,**kwargs):
    return SimpleNamespace(hardware=np.zeros((4,1)),smooth=np.zeros((4,1)),labels=[0,1],
        members=[0,1],supported=[],phase_sigma=np.array([2.,3.]),values=np.array([2.,3.,4.,5.]),
        q=np.ones(4),point_noise=np.ones(4)*100,noise_groups=np.array([0,0,1,1]))


def fake_calculate(p,x):
    features=np.zeros((4,6));features[:,0]=5
    features[:2,4]=1000;features[2:,5]=1000
    return dict(features=features,intercept=np.zeros(4))


def test_prior_mean_in_seconds_does_not_shrink_with_the_sigma_multiplier(monkeypatch):
    monkeypatch.setattr(learned,'problem',fake_problem)
    monkeypatch.setattr(learned.JointMarginal,'calculate',fake_calculate)
    keep=np.ones(4,bool);mu=np.array([1.,-2.])
    p=learned.make_problem(None,None,keep,'c0',np.zeros(2),np.ones(2),mu,.5,3.)
    result=p.calculate([0,0])
    # With zero phase sensitivity, posterior physical means equal prior means.
    assert result['coefficient'][2:4]*p.phase_sigma==pytest.approx(mu)
    assert np.isfinite(result['coefficient_prior_precision']).all()


def test_zero_mean_gaussian_fallback_exactly_matches_fragment300_control(monkeypatch):
    monkeypatch.setattr(learned,'problem',fake_problem)
    monkeypatch.setattr(controls,'problem',fake_problem)
    monkeypatch.setattr(learned.JointMarginal,'calculate',fake_calculate)
    keep=np.ones(4,bool);weights=np.array([1.,.2])
    a=learned.make_problem(None,None,keep,'c0',np.zeros(2),weights,np.zeros(2),1.,None).calculate([0,0])
    b=controls.controlled_problem(None,None,keep,'c0',np.zeros(2),weights,'fragment300').calculate([0,0])
    assert a['coefficient']==pytest.approx(b['coefficient'])
    assert a['negative_twice_elbo']==pytest.approx(b['negative_twice_elbo'])
