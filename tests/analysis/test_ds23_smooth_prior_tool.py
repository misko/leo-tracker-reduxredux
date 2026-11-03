"""Changing a covariance scale must preserve native mean/precision coordinates."""

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"tools"))
from probe_ds23_receiver_smooth_prior import scale_posterior


def test_quarter_scale_preserves_original_design_prediction_and_prior_cost():
    c=np.array([2.,3.,4.]);s=np.array([1.,.25,1.])
    prior=np.array([1.,2.,3.])
    result=scale_posterior(dict(coefficient=c.copy(),coefficient_prior_precision=prior.copy()),s)
    assert result['coefficient']==pytest.approx(c*s)
    assert np.sum(result['coefficient']**2*result['coefficient_prior_precision'])==pytest.approx(np.sum(c*c*prior))


def test_removed_mode_has_zero_mean_and_finite_prior_bookkeeping():
    r=scale_posterior(dict(coefficient=np.array([0.,2.]),coefficient_prior_precision=np.ones(2)),np.array([0.,1.]))
    assert np.isfinite(r['coefficient_prior_precision']).all()
    assert r['coefficient'][0]==0
