"""Curvature needs measured nonlinear evidence, beyond a fitted polynomial order."""

import sys
from pathlib import Path
import numpy as np
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools'))
from probe_ds23_statistical_curvature import curvature_evidence,active_ids
from types import SimpleNamespace


def test_linear_signal_with_radio_noise_does_not_calibrate():
    t=np.linspace(0,60,80);noise=np.full(80,40.);rng=np.random.default_rng(431)
    assert not curvature_evidence(t,1000+20*t+rng.normal(0,40,len(t)),noise)['eligible']


def test_statistically_clear_curve_below_old_250Hz_amplitude_is_supported():
    t=np.linspace(0,60,100);rng=np.random.default_rng(432);noise=np.full(100,40.)
    y=1000+20*t+.2*(t-30)**2+rng.normal(0,40,len(t))
    result=curvature_evidence(t,y,noise)
    assert result['eligible'] and result['delta_BIC']>10 and result['nonlinear_RMS_hz']<250


def test_short_or_sparse_curve_cannot_calibrate():
    assert not curvature_evidence(np.arange(10),np.arange(10)**2,np.ones(10)*40)['eligible']


def test_duplicate_active_observation_cannot_be_promoted_twice():
    scan=SimpleNamespace(tracks=[dict(key='a',observation_ids=['1','2']),dict(key='b',observation_ids=['2','3'])])
    node=dict(seed=dict(rows=[dict(component='a',active_curvature=True),dict(component='b',active_curvature=True)]))
    with pytest.raises(ValueError):active_ids(scan,node,np.ones(4,bool))
    assert active_ids(scan,node,np.array([True,False,True,True]))=={'1','2','3'}
