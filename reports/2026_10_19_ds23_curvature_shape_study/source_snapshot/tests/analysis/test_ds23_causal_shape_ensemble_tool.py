"""Causal ensembling distinguishes averaging noisy fits from trend extrapolation."""

import sys
from pathlib import Path
import numpy as np
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools'))
from learn_ds23_causal_shape_ensemble import select
from probe_ds23_causal_shape_ensemble import forecast_bank


def test_positive_update_correlation_selects_interpolation():
    row=dict(old_shape=np.ones((3,6)),next_shape=.5*np.ones((3,6)),scale=np.ones((3,6)),age_gap_ratio=1.)
    model=select([row]*100)
    assert model['mode']=='interpolate' and model['strength']==.5


def test_opposite_update_correlation_selects_extrapolation():
    row=dict(old_shape=np.ones((3,6)),next_shape=-.5*np.ones((3,6)),scale=np.ones((3,6)),age_gap_ratio=1.)
    model=select([row]*100)
    assert model['mode']=='extrapolate' and model['strength']==.5


def test_forecast_changes_state_mean_without_mutating_inputs():
    current=dict(time_s=np.array([0.,1.]),position_km=np.ones((1,2,3)),velocity_km_s=np.ones((1,2,3)))
    old=dict(time_s=current['time_s'],position_km=current['position_km']+2,velocity_km_s=current['velocity_km_s']+4)
    new=forecast_bank(current,old,[.25])
    assert new['position_km']==pytest.approx(np.ones((1,2,3))*1.5)
    assert new['velocity_km_s']==pytest.approx(np.ones((1,2,3))*2.)
    assert current['position_km']==pytest.approx(np.ones((1,2,3)))


def test_zero_forecast_reproduces_nominal_bank_exactly():
    current=dict(time_s=np.array([0.,1.]),position_km=np.ones((1,2,3)),velocity_km_s=np.ones((1,2,3)))
    old=dict(time_s=current['time_s'],position_km=current['position_km']+2,velocity_km_s=current['velocity_km_s']+4)
    assert np.array_equal(forecast_bank(current,old,[0])['position_km'],current['position_km'])
